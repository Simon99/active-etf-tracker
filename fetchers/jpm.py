"""摩根投信 (am.jpmorgan.com/tw) — GET /FundsMarketingHandler/product-data。

ETF 對照（ISIN = TW + ETF code + Luhn check digit）：
  00989A 摩根大美國領先科技主動式ETF → TW00000989A5  (持美股)
  00401A 摩根收益進化台灣起飛主動式ETF → TW00000401A1  (持台股)

API:
  GET https://am.jpmorgan.com/FundsMarketingHandler/product-data
      ?cusip=<ISIN>&country=tw&role=twetf&language=zh
  Response (nested deep):
    fundData[?].holdings.pcfEquityHoldings.data[*] = {
      securityDescription, securityTicker, securityCusip,
      shares, marketValuePercent, marketValue,
      navDate, effectiveDate, securityType, assetType, ...
    }
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://am.jpmorgan.com/FundsMarketingHandler/product-data'

REGISTRY = {
    '00989A': (None, 'TW00000989A5'),
    '00401A': (None, 'TW00000401A1'),
}


def fetch(etf_id: str, isin: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Accept': 'application/json',
        'Referer': 'https://am.jpmorgan.com/tw/zh/asset-management/twetf/',
    }
    params = {'cusip': isin, 'country': 'tw', 'role': 'twetf', 'language': 'zh'}

    try:
        r = requests.get(API_URL, params=params, headers=headers, timeout=30)
    except requests.RequestException as e:
        res.error = f'request failed: {e}'
        return res

    if r.status_code != 200:
        res.error = f'http {r.status_code}'
        return res

    try:
        data = r.json()
    except ValueError as e:
        res.error = f'json decode: {e}'
        return res

    if data.get('error'):
        res.error = f'api error: {data["error"]}'
        return res

    # fundData 是 list (通常一筆)
    fund_list = data.get('fundData') or []
    if not fund_list:
        res.error = 'no fundData'
        return res
    fund = fund_list[0] if isinstance(fund_list, list) else fund_list

    holdings_block = (fund.get('holdings') or {}).get('pcfEquityHoldings') or {}
    rows = holdings_block.get('data') or []

    if not rows:
        res.error = f'no pcfEquityHoldings.data (effectiveDate={holdings_block.get("effectiveDate")})'
        return res

    nav_date = holdings_block.get('effectiveDate')
    # fund 基本資料（基金規模、單位數 等可能藏在不同 key，但 PCF 已足夠）
    res.meta = {
        'PCF 基準日': nav_date,
        '持股筆數': len(rows),
        'fund 描述 keys': list(fund.keys())[:10],
    }

    holdings = []
    for r_ in rows:
        ticker = (r_.get('securityTicker') or '').strip()
        desc = (r_.get('securityDescription') or '').strip()
        # 過濾 cash / 非個股
        if not ticker or r_.get('securityType') not in ('Equity', None):
            # 有的 holdings 可能是 cash equivalent，跳過非 Equity
            if r_.get('securityType') and 'equity' not in r_.get('securityType', '').lower():
                continue
        if not ticker:
            continue
        # 台股 ticker 是純數字代碼；美股可能是英文
        stock_id = ticker
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': desc,
            'shares': _to_int(r_.get('shares')),
            'weight': _to_float(r_.get('marketValuePercent')),
            'market_value': _to_float(r_.get('marketValue')),
        })

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
