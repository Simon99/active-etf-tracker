"""野村投信 (nomurafunds.com.tw) — POST /API/ETFAPI/api/Fund/GetFundAssets。

ETF 對照（直接用 ETF code 當 FundID 即可，無需轉換）：
  00980A 主動野村臺灣優選
  00985A 主動野村台灣50
  00999A 主動野村臺灣高息

API:
  POST https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets
  Body: {"FundID":"00980A","SearchDate":null}
  Response:
    Entries.Data.FundAsset = {Aum, Units, Nav, NavDate}
    Entries.Data.Table[0].Rows = [[stocNo, stocName, shares, weight%], ...]
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets'

REGISTRY = {
    '00980A': (None, '00980A'),
    '00985A': (None, '00985A'),
    '00999A': (None, '00999A'),
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.nomurafunds.com.tw',
        'Referer': f'https://www.nomurafunds.com.tw/ETFWEB/product-description?fundNo={fund_id}&tab=Shareholding',
    }
    body = {'FundID': fund_id, 'SearchDate': None}

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

    entries = (data.get('Entries') or {}).get('Data') or {}
    asset = entries.get('FundAsset') or {}
    tables = entries.get('Table') or []

    # 找「股票」表（理論上 index 0，保險起見搜尋）
    stock_table = next((t for t in tables if t.get('TableTitle') == '股票'), tables[0] if tables else None)
    if not stock_table:
        res.error = 'no stock table in response'
        return res

    res.meta = {
        '基金規模(元)': asset.get('Aum'),
        '已發行受益權單位總數': asset.get('Units'),
        '每受益權單位淨資產價值(元)': asset.get('Nav'),
        'NAV 日期': asset.get('NavDate'),
    }

    holdings = []
    for row in stock_table.get('Rows') or []:
        if len(row) < 4:
            continue
        stock_id = (row[0] or '').strip()
        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (row[1] or '').strip(),
            'shares': _to_int(row[2]),
            'weight': _to_float(row[3]),
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
