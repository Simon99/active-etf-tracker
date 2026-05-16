"""復華投信 (fhtrust.com.tw) — GET /api/assets?fundID=ETFxx&qDate=YYYY/MM/DD。

ETF 對照（從 /api/fundList 的 etf002 + fundID 撈出）：
  00991A 復華台灣未來50主動式ETF        → ETF23
  00998A 復華全球金融股票入息主動式ETF  → ETF24

API:
  GET https://www.fhtrust.com.tw/api/assets?fundID=ETF23&qDate=2026/05/15
  Response.result[0] = {
    fundID, etf002, dDate, pcf_FundNav, pcf_FundQissue, pcf_Fundpnav,
    result:  [asset-class 匯總 3 行],
    summary: [asset-class % 2 行],
    detail:  [<--- 真正的個股清單在這 ---> {ftype, stockid, stockname, qshare, mvalue, price, prate_addaccint, ...}],
    diff:    [],
    rate:    [...]
  }
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://www.fhtrust.com.tw/api/assets'

REGISTRY = {
    '00991A': (None, 'ETF23'),
    '00998A': (None, 'ETF24'),
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {'User-Agent': UA, 'Accept': 'application/json',
               'Referer': f'https://www.fhtrust.com.tw/ETF/etf_detail/{fund_id}'}

    # 復華 qDate 用 YYYY/MM/DD；週末 fallback 前 N 天
    payload = None
    settle_date = None
    for offset in range(0, 7):
        d = date - dt.timedelta(days=offset)
        qd = d.strftime('%Y/%m/%d')
        try:
            r = requests.get(API_URL, params={'fundID': fund_id, 'qDate': qd},
                             headers=headers, timeout=20)
        except requests.RequestException as e:
            res.error = f'request failed: {e}'
            return res
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except ValueError:
            continue
        results = body.get('result') or []
        if not results:
            continue
        row = results[0]
        if row.get('detail'):
            payload = row
            settle_date = d.isoformat()
            break

    if not payload:
        res.error = 'no detail in last 7 days'
        return res

    res.meta = {
        'PCF settle date': settle_date,
        '基金規模(元)': payload.get('pcf_FundNav'),
        '已發行受益權單位總數': payload.get('pcf_FundQissue'),
        '每受益權單位淨資產價值(元)': payload.get('pcf_Fundpnav'),
        'dDate': payload.get('dDate'),
    }

    holdings = []
    for row in payload.get('detail') or []:
        if row.get('ftype') != '股票':
            continue
        raw_id = (row.get('stockid') or '').strip()
        # "LGEN LN" / "TSLA US" / "2330" → 去掉市場後綴 (任何 2-letter 國家碼)
        m = re.match(r'^([0-9A-Z.]+)\s+([A-Z]{2})$', raw_id)
        stock_id = m.group(1) if m else raw_id
        if not re.match(r'^[0-9A-Z.]{1,12}$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (row.get('stockname') or '').strip(),
            'shares': _to_int(row.get('qshare')),
            'weight': _to_float(row.get('prate_addaccint')),
            'market_value': _to_float(row.get('mvalue')),
        })

    if not holdings:
        res.error = 'no stock rows in detail'
        return res

    res.holdings = holdings
    return res


def _to_int(v):
    if v is None:
        return None
    try:
        return int(float(str(v).replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


def _to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace('%', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return None


import sys as _sys
_self = _sys.modules[__name__]
REGISTRY = {k: (_self, v[1]) for k, v in REGISTRY.items()}
