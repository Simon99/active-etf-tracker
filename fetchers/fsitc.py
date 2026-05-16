"""第一金投信 (fsitc.com.tw) — POST /WebAPI.aspx/Get_hd。

ETF 對照（基金頁面 URL ID）：
  00994A 主動第一金台股趨勢優選 → 182

API:
  POST https://www.fsitc.com.tw/WebAPI.aspx/Get_hd
  Content-Type: application/json
  Body (literal — note the leading space, single quotes used by site):
      { 'pStrFundID':'182','pStrDate':''}
  Response: {"d": "[<JSON-encoded array string>]"}
  Inner row: {fundid, sdate, group, A=stock_id, B=stock_name, C=weight%, D=shares, E}
"""
from __future__ import annotations

import datetime as dt
import json
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://www.fsitc.com.tw/WebAPI.aspx/Get_hd'

REGISTRY = {
    '00994A': (None, '182'),
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.fsitc.com.tw',
        'Referer': f'https://www.fsitc.com.tw/FundDetail.aspx?ID={fund_id}',
    }
    body = "{ 'pStrFundID':'%s','pStrDate':''}" % fund_id

    try:
        r = requests.post(API_URL, data=body, headers=headers, timeout=20)
    except requests.RequestException as e:
        res.error = f'request failed: {e}'
        return res

    if r.status_code != 200:
        res.error = f'http {r.status_code}'
        return res

    try:
        outer = r.json()
        inner = json.loads(outer.get('d') or '[]')
    except (ValueError, TypeError) as e:
        res.error = f'json decode: {e}'
        return res

    if not inner:
        res.error = 'empty data'
        return res

    sdate = (inner[0] or {}).get('sdate') or ''

    res.meta = {
        '基金 ID': fund_id,
        '資料日期': sdate,
    }

    holdings = []
    for row in inner:
        stock_id = (row.get('A') or '').strip()
        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (row.get('B') or '').strip(),
            'shares': _to_int(row.get('D')),
            'weight': _to_float(row.get('C')),
            'market_value': None,
        })

    res.holdings = holdings
    return res


def _to_int(v):
    if v is None:
        return None
    s = str(v).replace(',', '').strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _to_float(v):
    if v is None:
        return None
    s = str(v).replace('%', '').replace(',', '').strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


import sys as _sys
_self = _sys.modules[__name__]
REGISTRY = {k: (_self, v[1]) for k, v in REGISTRY.items()}
