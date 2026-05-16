"""兆豐投信 (megafunds.com.tw) — server-side rendered HTML，直接 GET 整頁解析。

ETF 對照（內部 fund id 是頁面 URL 上的 id 數字）：
  00996A 主動兆豐台灣豐收 → id 23

URL:
  GET https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id=23

頁面持股 row 結構（server rendered，無 XHR）：
  <div class="fund-info content-list-1">
    <div class="fund-content">2330</div>          <-- stock_id
    <div class="fund-content">台積電</div>          <-- name
    <div class="fund-content txt-right">179,000</div>  <-- shares
    <div class="fund-content txt-right">8.79 %</div>   <-- weight
  </div>
"""
from __future__ import annotations

import datetime as dt
import re
import requests
from bs4 import BeautifulSoup

from .base import FetchResult, UA

REGISTRY = {
    '00996A': (None, '23'),
}


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {'User-Agent': UA, 'Accept': 'text/html'}

    try:
        r = requests.get(
            'https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx',
            params={'id': fund_id},
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as e:
        res.error = f'request failed: {e}'
        return res

    if r.status_code != 200:
        res.error = f'http {r.status_code}'
        return res

    soup = BeautifulSoup(r.text, 'html.parser')
    rows = soup.select('div.fund-info.content-list-1')

    holdings = []
    for row in rows:
        cells = row.select('div.fund-content')
        if len(cells) < 4:
            continue
        stock_id = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
        shares_txt = cells[2].get_text(strip=True)
        weight_txt = cells[3].get_text(strip=True)

        if not re.match(r'^\d{4,6}[A-Z]?$', stock_id):
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': name,
            'shares': _to_int(shares_txt),
            'weight': _to_float(weight_txt),
            'market_value': None,
        })

    if not holdings:
        res.error = 'no holdings row parsed'
        return res

    # 資料日期（"資料來源：兆豐投信，2026/05/15"）
    date_match = re.search(r'資料來源[^，]*，\s*(\d{4}/\d{2}/\d{2})', r.text)
    res.meta = {
        '資料日期': date_match.group(1) if date_match else None,
        '持股筆數': len(holdings),
    }
    res.holdings = holdings
    return res


def _to_int(s):
    if not s:
        return None
    try:
        return int(float(s.replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


def _to_float(s):
    if not s:
        return None
    try:
        return float(s.replace('%', '').replace(',', '').strip())
    except (ValueError, TypeError):
        return None


import sys as _sys
_self = _sys.modules[__name__]
REGISTRY = {k: (_self, v[1]) for k, v in REGISTRY.items()}
