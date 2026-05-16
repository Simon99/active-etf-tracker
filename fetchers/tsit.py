"""台新投信 (tsit.com.tw) — GET /ETF/Home/Pcf?id=<etf_id>。

ETF 對照（直接用 ETF code 當 id）：
  00986A 主動台新全球龍頭成長
  00987A 主動台新優勢成長

API:
  GET https://www.tsit.com.tw/ETF/Home/Pcf?id=00986A
  Response: HTML 全頁，持股 row 樣式：
    <tr>
      <td>2330 TT</td>     <-- ticker + market suffix
      <td>台積電</td>       <-- 中文名稱
      <td>22,000</td>      <-- 股數
      <td>7.7004%</td>     <-- 權重
    </tr>
"""
from __future__ import annotations

import datetime as dt
import re
import requests
from bs4 import BeautifulSoup

from .base import FetchResult, UA

API_URL = 'https://www.tsit.com.tw/ETF/Home/Pcf'

REGISTRY = {
    '00986A': (None, '00986A'),
    '00987A': (None, '00987A'),
}

# 把 "2330 TT", "LITE US" 之類拆成 ticker + market suffix
TICKER_RE = re.compile(r'^([0-9A-Z.]+)\s+(TT|US|HK|JP|UK|GR|FP|CN)$', re.IGNORECASE)


def fetch(etf_id: str, fund_id: str, date: dt.date) -> FetchResult:
    res = FetchResult(etf_id=etf_id, date=date)
    headers = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Referer': f'https://www.tsit.com.tw/ETF/Home/ETFSeriesDetail/{fund_id}',
    }

    try:
        r = requests.get(API_URL, params={'id': fund_id}, headers=headers, timeout=20)
    except requests.RequestException as e:
        res.error = f'request failed: {e}'
        return res

    if r.status_code != 200:
        res.error = f'http {r.status_code}'
        return res

    soup = BeautifulSoup(r.text, 'html.parser')
    holdings = []
    # 掃所有 4-cell <tr>
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) != 4:
            continue
        raw_ticker = tds[0].get_text(strip=True)
        m = TICKER_RE.match(raw_ticker)
        if m:
            stock_id = m.group(1)
        else:
            # 純台股代號 (如 2330) 或不含 market 後綴 → 試直接當 ticker
            stock_id = raw_ticker
        if not re.match(r'^[0-9A-Z.]{1,12}$', stock_id):
            continue
        name = tds[1].get_text(strip=True)
        shares = _to_int(tds[2].get_text(strip=True))
        weight = _to_float(tds[3].get_text(strip=True))
        # 過濾不像個股的列（純文字標題、總計列等）
        if shares is None and weight is None:
            continue
        holdings.append({
            'date': date.isoformat(),
            'etf_id': etf_id,
            'stock_id': stock_id,
            'stock_name': name,
            'shares': shares,
            'weight': weight,
            'market_value': None,
        })

    if not holdings:
        res.error = 'no holdings row parsed'
        return res

    res.meta = {'持股筆數': len(holdings), 'source': 'tsit HTML'}
    res.holdings = holdings
    return res


def _to_int(s):
    if not s:
        return None
    s = s.replace(',', '').strip()
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _to_float(s):
    if not s:
        return None
    s = s.replace('%', '').replace(',', '').strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


import sys as _sys
_self = _sys.modules[__name__]
REGISTRY = {k: (_self, v[1]) for k, v in REGISTRY.items()}
