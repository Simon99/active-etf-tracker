"""Probe an issuer's ETF page with headless Chrome to find the PCF / holdings XHR.

Usage:
    .venv/bin/python scripts/probe_issuer.py <url>

Loads URL in headless Chromium, records every XHR/fetch request, classifies
which response looks like a holdings list (contains stock_id patterns 2330/台積電 etc.),
then prints a compact report:

    [ENDPOINT 1/N] POST https://.../api/...
      body: {...}
      response keys: [...]
      holdings detected: 50  (rows look like [stocNo, stocName, shares, weight])
      curl: <reproducible bash one-liner>

That report is enough to write a fetcher without ever opening DevTools manually.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
)

STOCK_ID_RE = re.compile(r'\b\d{4,5}[A-Z]?\b')
HOLDING_KEYWORDS = ('股票代號', '股票代碼', 'stocNo', 'StockNo', '股票名稱',
                    'stocName', 'StockName', 'weight', 'Weight', 'share', 'Share',
                    '持股權重', '持股比重', 'holdings', 'Holdings')


def score_response(text: str) -> tuple[int, int]:
    """Return (signal_score, n_stock_ids). Higher = more likely a PCF endpoint."""
    if not text or len(text) < 50:
        return 0, 0
    n_stock = len(set(STOCK_ID_RE.findall(text)))
    kw = sum(1 for k in HOLDING_KEYWORDS if k in text)
    # 簡單啟發：≥5 個不同 stock_id + 至少 1 個 holding keyword
    signal = kw * 2 + (n_stock if n_stock >= 5 else 0)
    return signal, n_stock


def request_to_curl(req, body: str | None) -> str:
    parts = ['curl', shlex.quote(req.url)]
    if req.method != 'GET':
        parts += ['-X', req.method]
    for k, v in (req.headers or {}).items():
        if k.lower() in ('cookie', 'host', 'content-length', 'accept-encoding'):
            continue
        parts += ['-H', shlex.quote(f'{k}: {v}')]
    if body:
        parts += ['--data-raw', shlex.quote(body)]
    return ' '.join(parts)


# 各家投信「持股」tab 常見字樣
HOLDING_TAB_KEYWORDS = (
    '持股比重', '持股明細', '持股', '投資組合', '成份股', '成分股',
    '申購買回', 'Shareholding', 'Holdings', 'Portfolio', 'PCF',
)


def probe(url: str, timeout_ms: int = 30000, wait_idle_ms: int = 3000):
    captures: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale='zh-TW')
        page = ctx.new_page()

        def on_response(resp):
            req = resp.request
            if req.resource_type not in ('xhr', 'fetch'):
                return
            try:
                body = resp.text()
            except Exception:
                body = ''
            if not body:
                return
            score, n_stock = score_response(body)
            captures.append({
                'method': req.method,
                'url': req.url,
                'status': resp.status,
                'req_headers': dict(req.headers or {}),
                'req_body': req.post_data,
                'resp_ct': resp.headers.get('content-type', ''),
                'resp_len': len(body),
                'resp_body': body,
                'score': score,
                'n_stock': n_stock,
            })

        page.on('response', on_response)
        try:
            page.goto(url, timeout=timeout_ms, wait_until='networkidle')
        except Exception as e:
            print(f'[warn] goto: {e}', file=sys.stderr)
        page.wait_for_timeout(wait_idle_ms)

        # 嘗試點擊「持股」分頁 (SPA 常要點擊才觸發 XHR)
        for kw in HOLDING_TAB_KEYWORDS:
            try:
                # 同時試 link / button / tab role
                loc = page.get_by_text(kw, exact=False).first
                if loc.count() > 0:
                    loc.click(timeout=2000)
                    page.wait_for_timeout(2500)
                    break
            except Exception:
                continue

        # 滾到底，順手觸發 lazy load
        try:
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(1500)
        except Exception:
            pass

        browser.close()

    return captures


def report(url: str, captures: list[dict]) -> None:
    print(f'━━━ probed {url} ━━━')
    print(f'  total XHR/fetch captured: {len(captures)}')
    candidates = sorted(
        [c for c in captures if c['score'] >= 5],
        key=lambda c: c['score'],
        reverse=True,
    )
    print(f'  PCF-like candidates: {len(candidates)} (score ≥ 5)\n')

    for i, c in enumerate(candidates[:5], 1):
        print(f'[CANDIDATE {i}/{len(candidates)}] score={c["score"]}  '
              f'stock_ids={c["n_stock"]}  status={c["status"]}  len={c["resp_len"]}')
        print(f'  {c["method"]} {c["url"]}')
        if c['req_body']:
            print(f'  body: {c["req_body"]}')
        # response 結構摘要
        try:
            j = json.loads(c['resp_body'])
            print(f'  resp keys: {list(j.keys()) if isinstance(j, dict) else type(j).__name__}')
            print(f'  resp head: {json.dumps(j, ensure_ascii=False)[:300]}')
        except Exception:
            print(f'  resp head: {c["resp_body"][:300]}')
        # 樣本 stock_id
        sample = sorted(set(STOCK_ID_RE.findall(c['resp_body'])))[:8]
        print(f'  sample stock_ids: {sample}')
        print()


def main():
    if len(sys.argv) < 2:
        print('usage: probe_issuer.py <url> [<url2> ...]')
        sys.exit(1)
    for url in sys.argv[1:]:
        caps = probe(url)
        report(url, caps)
        print()


if __name__ == '__main__':
    main()
