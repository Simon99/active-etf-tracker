"""群益投信 (capitalfund.com.tw) — POST /CFWeb/api/etf/buyback。

ETF 對照 (從 /etf/product/detail/<fundId>/buyback 頁面的 <option> 抓):
  00982A 主動群益台灣強棒    → fundId 399
  00992A 主動群益科技創新    → fundId 500
  00997A 主動群益美國增長    → fundId 502

API:
  POST https://www.capitalfund.com.tw/CFWeb/api/etf/buyback
  Body: {"fundId":"399","date":null}    # date=null 拿最新
  Response: { code, data: { pcf: {...metadata}, stocks: [...] }, message }
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://www.capitalfund.com.tw/CFWeb/api/etf/buyback'

REGISTRY = {
    '00982A': (None, '399'),
    '00992A': (None, '500'),
    '00997A': (None, '502'),
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.capitalfund.com.tw',
        'Referer': f'https://www.capitalfund.com.tw/etf/product/detail/{fund_id}/buyback',
    }
    # 群益 API 只回「最新一日」資料，date 參數似乎沒實際過濾效果，故只用 date=null
    body = {'fundId': fund_id, 'date': None}

    try:
        r = requests.post(API_URL, json=body, headers=headers, timeout=20)
    except requests.RequestException as e:
        res.error = f'request failed: {e}'
        return res

    if r.status_code != 200 or 'json' not in (r.headers.get('content-type') or ''):
        res.error = f'http {r.status_code} ct={r.headers.get("content-type")}'
        return res

    try:
        data = r.json()
    except ValueError as e:
        res.error = f'json decode: {e}'
        return res

    if data.get('code') != 200:
        res.error = f'api code {data.get("code")} msg={data.get("message")}'
        return res

    payload = data.get('data') or {}
    pcf = payload.get('pcf') or {}
    stocks = payload.get('stocks') or []

    # 入庫一律用「抓取當天」(date)，與其他 fetcher 保持一致；
    # PCF settle date (date1, 通常 T+2) 另存於 meta 供參考
    pcf_settle = _parse_date(pcf.get('date1'))

    res.meta = {
        '基金名稱': pcf.get('fundName'),
        'PCF settle date (T+2)': pcf_settle.isoformat() if pcf_settle else None,
        '前一交易日': pcf.get('date2'),
        '基金淨資產價值(元)': pcf.get('nav'),
        '已發行受益權單位總數': pcf.get('totUnit'),
        '每受益權單位淨資產價值(元)': pcf.get('pUnit'),
        '預收申購總價金(元)': pcf.get('forecastAmt'),
        '每現金申購/買回基數之受益權單位數': pcf.get('tUnit'),
    }

    holdings = []
    for s in stocks:
        stock_id = (s.get('stocNo') or '').strip()
        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (s.get('stocName') or '').strip(),
            'shares': int(s['share']) if s.get('share') is not None else None,
            'weight': float(s['weight']) if s.get('weight') is not None else None,
            'market_value': None,
        })

    res.holdings = holdings
    return res


def _parse_date(s):
    if not s:
        return None
    # 期望 '2026-05-18' 或 '2026/05/18'
    s = str(s).strip().split(' ')[0].replace('/', '-')
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


import sys as _sys
_self = _sys.modules[__name__]
REGISTRY = {k: (_self, v[1]) for k, v in REGISTRY.items()}
