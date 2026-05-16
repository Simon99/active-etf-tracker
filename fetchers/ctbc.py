"""中信投信 (ctbcinvestments.com.tw) — POST /API/etf/Buyback。

需先 POST AuthToken 拿 token，再帶 token URL param 呼叫 Buyback。

ETF 對照（從 ETFCNOList API 撈出）：
  00983A 主動中信ARK創新   → FID E0034  (CNO 00586267)
  00995A 主動中信台灣卓越  → FID E0036  (CNO 00653201)

API flow:
  POST https://www.ctbcinvestments.com.tw/API/home/AuthToken?token=www.ctbcinvestments.com
    body: {}
    response: {Data: {token: "..."}}
  POST https://www.ctbcinvestments.com.tw/API/etf/Buyback?token=<url-encoded token>
    body: {"FID":"E0034","StartDate":"2026-05-15"}
    response: {Data: {Data: [<metadata>], Detail: [{Data: [<stocks>]}, ...]}}

  stock row keys: invtp_, code_, name_, qty_, weights_, amount_, price_
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
import requests

from .base import FetchResult, UA

BASE = 'https://www.ctbcinvestments.com.tw'
TOKEN_URL = f'{BASE}/API/home/AuthToken?token=www.ctbcinvestments.com'
BUYBACK_URL = f'{BASE}/API/etf/Buyback'

REGISTRY = {
    '00983A': (None, 'E0034'),
    '00995A': (None, 'E0036'),
}


def fetch(etf_id: str, fid: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers_base = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.ctbcinvestments.com',
        'Referer': 'https://www.ctbcinvestments.com/',
    }

    # 1) AuthToken
    try:
        r = requests.post(TOKEN_URL, json={}, headers=headers_base, timeout=15)
        token = (r.json().get('Data') or {}).get('token')
    except Exception as e:
        res.error = f'AuthToken failed: {e}'
        return res
    if not token:
        res.error = 'no token in AuthToken response'
        return res

    # 2) Buyback — fallback 前 N 天找最近交易日
    encoded = urllib.parse.quote(token, safe='')
    url = f'{BUYBACK_URL}?token={encoded}'
    payload = None
    settle_date = None
    for offset in range(0, 7):
        d = date - dt.timedelta(days=offset)
        body = {'FID': fid, 'StartDate': d.isoformat()}
        try:
            r = requests.post(url, json=body, headers=headers_base, timeout=15)
        except requests.RequestException as e:
            res.error = f'Buyback request failed: {e}'
            return res
        if r.status_code != 200:
            continue
        data = (r.json() or {}).get('Data') or {}
        rows = data.get('Data') or []
        details = data.get('Detail') or []
        if rows and details:
            payload = (rows[0], details)
            settle_date = d.isoformat()
            break

    if not payload:
        res.error = 'no data in last 7 days'
        return res

    meta_row, details = payload

    res.meta = {
        'PCF settle date': settle_date,
        '基金名稱': meta_row.get('FundName'),
        '基金淨資產價值(元)': meta_row.get('基金淨資產價值'),
        '已發行受益權單位總數': meta_row.get('已發行受益權單位總數'),
        '每受益權單位淨資產價值(元)': meta_row.get('每受益權單位淨資產價值'),
        'NAV 日期': meta_row.get('淨值日期'),
    }

    holdings = []
    for section in details:
        # 只抓「股票」section（Code=STOCK），忽略現金 / 其他
        if section.get('Code') != 'STOCK':
            continue
        for row in section.get('Data') or []:
            raw_code = (row.get('code_') or '').strip()
            # "TSLA US" / "2330 TT" / "2330" → 去市場後綴
            m = re.match(r'^([0-9A-Z.]+)\s+(TT|US|HK|JP|UK|GR|FP|CN)$', raw_code, re.IGNORECASE)
            stock_id = m.group(1) if m else raw_code
            if not re.match(r'^[0-9A-Z.]{1,12}$', stock_id):
                continue
            holdings.append({
                'date': date.isoformat(),
                'etf_id': etf_id,
                'stock_id': stock_id,
                'stock_name': (row.get('name_') or '').strip(),
                'shares': _to_int(row.get('qty_')),
                'weight': _to_float(row.get('weights_')),
                'market_value': _to_float(row.get('amount_')),
            })

    if not holdings:
        res.error = 'no holdings parsed'
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
