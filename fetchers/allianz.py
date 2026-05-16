"""安聯投信 (etf.allianzgi.com.tw) — POST /webapi/api/Fund/GetFundAssets。

需先 GET AntiForgery token endpoint 以拿 XSRF cookie，再把 cookie 中
`X-XSRF-TOKEN` 同時放回 X-XSRF-TOKEN header（雙重提交防 CSRF）。

ETF 對照（FundID 是內部代號 E0001 / E0002 …，不等於上市代號）：
  00984A 安聯台灣高息成長 → FundID E0001  (已確認)
  00993A 主動安聯台灣      → FundID 未確認

API:
  GET  /webapi/api/AntiForgery/GetAntiForgeryToken    (拿 XSRF cookie)
  POST /webapi/api/Fund/GetFundAssets
    Body: {"FundID":"E0001"}
  Response:
    Entries.Data.FundAsset = {Aum, Units, Nav, NavDate, PCFDate}
    Entries.Data.Table[*]  = [ {TableTitle, Rows: [[序號, stocNo, stocName, shares, weight%], ...]} ]
"""
from __future__ import annotations

import datetime as dt
import re
import requests

from .base import FetchResult, UA

BASE = 'https://etf.allianzgi.com.tw'
TOKEN_URL = f'{BASE}/webapi/api/AntiForgery/GetAntiForgeryToken'
ASSETS_URL = f'{BASE}/webapi/api/Fund/GetFundAssets'

REGISTRY = {
    '00984A': (None, 'E0001'),
    # '00993A': (None, 'E????'),  # 等確認後加入
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    s = requests.Session()
    s.headers.update({'User-Agent': UA})

    try:
        s.get(TOKEN_URL,
              headers={'Referer': f'{BASE}/etf-info/{fund_id}?tab=4'},
              timeout=15)
    except requests.RequestException as e:
        res.error = f'antiforgery failed: {e}'
        return res

    xsrf = s.cookies.get('X-XSRF-TOKEN')
    if not xsrf:
        res.error = 'no X-XSRF-TOKEN cookie after antiforgery'
        return res

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': BASE,
        'Referer': f'{BASE}/etf-info/{fund_id}?tab=4',
        'X-XSRF-TOKEN': xsrf,
    }

    try:
        r = s.post(ASSETS_URL, json={'FundID': fund_id}, headers=headers, timeout=20)
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
    if not entries:
        res.error = data.get('Message') or 'empty Entries.Data'
        return res

    asset = entries.get('FundAsset') or {}
    tables = entries.get('Table') or []

    stock_table = next((t for t in tables if (t.get('TableTitle') or '').startswith('股票')), None)
    if not stock_table:
        res.error = 'no 股票 table in response'
        return res

    res.meta = {
        '基金規模(元)': asset.get('Aum'),
        '已發行受益權單位總數': asset.get('Units'),
        '每受益權單位淨資產價值(元)': asset.get('Nav'),
        'NAV 日期': asset.get('NavDate'),
        'PCF 日期': asset.get('PCFDate'),
    }

    holdings = []
    for row in stock_table.get('Rows') or []:
        # 安聯 row schema: [序號, stocNo, stocName, shares, weight%]
        if len(row) < 5:
            continue
        stock_id = (row[1] or '').strip()
        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': (row[2] or '').strip(),
            'shares': _to_int(row[3]),
            'weight': _to_float(row[4]),
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
