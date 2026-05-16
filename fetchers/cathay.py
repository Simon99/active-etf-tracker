"""國泰投信 (cathaysite.com.tw) — GET cwapi.cathaysite.com.tw/api/ETF/GetETFDetailStockList。

ETF 對照（FundCode 是內部 2 字母代碼）：
  00400A 主動國泰動能高息 → EA

API:
  GET https://cwapi.cathaysite.com.tw/api/ETF/GetETFDetailStockList?FundCode=EA&SearchDate=YYYY-MM-DD
  Response: {"result": [{stockCode, stockName, volumn, weights}, ...]}

Note: 頁面被 Akamai 防 bot，但直接打 cwapi 沒 Akamai，UA 像瀏覽器即可。
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

API_URL = 'https://cwapi.cathaysite.com.tw/api/ETF/GetETFDetailStockList'

REGISTRY = {
    '00400A': (None, 'EA'),
}


def fetch(etf_id: str, fund_code: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Accept': 'application/json',
        'Origin': 'https://www.cathaysite.com.tw',
        'Referer': f'https://www.cathaysite.com.tw/ETF/detail/E{fund_code}?tab=etf3',
    }

    # 國泰 API 只在交易日有料；週末 / 假日 retry 前 N 天
    rows = None
    settle_date = None
    for offset in range(0, 7):
        probe_date = date - dt.timedelta(days=offset)
        params = {'FundCode': fund_code, 'SearchDate': probe_date.isoformat()}
        try:
            r = requests.get(API_URL, params=params, headers=headers, timeout=20)
        except requests.RequestException as e:
            res.error = f'request failed: {e}'
            return res
        if r.status_code != 200 or 'json' not in (r.headers.get('content-type') or ''):
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        rows = data.get('result') or []
        if rows:
            settle_date = probe_date.isoformat()
            break

    if not rows:
        res.error = 'empty result for last 7 days'
        return res

    holdings = []
    for row in rows:
        stock_id = (row.get('stockCode') or '').strip()
        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (row.get('stockName') or '').strip().replace(' ', ''),
            'shares': _to_int(row.get('volumn')),
            'weight': _to_float(row.get('weights')),
            'market_value': None,
        })

    res.meta = {'持股筆數': len(holdings), 'PCF settle date': settle_date}
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
