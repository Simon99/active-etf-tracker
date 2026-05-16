"""產出每檔 ETF 一筆獨立 SKILL.md 到 ~/.claude/skills/etf-<id>/

從 etf_meta + holdings.db 抓現況，再依 issuer 套不同模板。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / 'data' / 'holdings.db'
SKILLS_DIR = Path(os.path.expanduser('~/.claude/skills'))

# 每 issuer 的「API 細節 + quirks + 排查」段落模板
# 變數: {etf_id} {fund_code}
ISSUER_TEMPLATES = {
    'uni': {
        'display': '統一投信 (ezmoney.com.tw)',
        'api': """\
```http
GET https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI
    ?fundCode={fund_code}
    &date=115/05/16          # 民國年/月/日 = 西元-1911
    &specificDate=false
Referer: https://www.ezmoney.com.tw/ETF/Transaction/PCF?fundCode={fund_code}
```

回應：Excel `.xlsx`（sheet 名「申購買回清單」）

| 行 | 內容 |
|---|---|
| 1-9 | 基金 metadata（NAV、單位數、淨資產） |
| 13 | 標題「股票」 |
| 14 | header: 股票代號 / 股票名稱 / 股數 / 持股權重 |
| 15+ | 持股 row |
""",
        'quirks': """\
- **error 偽 200**：失敗時回 HTTP 200 + HTML（`<span data-content="…">`），檢查 content-type 必為 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **民國年日期**：`date=115/05/16` 不是 `2026-05-16`
- **`specificDate=false` 必帶**
""",
        'triage': """\
1. n=0 / error 含 "not an excel" → 民國年日期錯，或漏帶 specificDate
2. error: HTTPError 403/1010 → UA 被 Cloudflare 擋，加 browser UA
3. error: 'header row 股票代號 not found' → Excel sheet 結構變了，看 `/tmp/{etf_id}_pcf.xlsx` 重新對齊
""",
    },
    'capital': {
        'display': '群益投信 (capitalfund.com.tw)',
        'api': """\
```http
POST https://www.capitalfund.com.tw/CFWeb/api/etf/buyback
Content-Type: application/json

{{"fundId":"{fund_code}","date":null}}
```

回應 JSON：`data.pcf` = 基金 metadata，`data.stocks` = 持股 list
""",
        'quirks': """\
- `date: null` 拿最新，傳具體 date 似乎沒過濾效果
- `date1` 是 PCF settle date (T+2)，`date2` 是前一交易日
""",
        'triage': """\
1. status 非 200 / ct 非 json → API 路徑變了，重 probe `scripts/probe_issuer.py <buyback URL>`
2. `data.code != 200` → 看 message
""",
    },
    'nomura': {
        'display': '野村投信 (nomurafunds.com.tw)',
        'api': """\
```http
POST https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets
Content-Type: application/json

{{"FundID":"{fund_code}","SearchDate":null}}
```

回應 `Entries.Data.Table[*]` 找 `TableTitle == '股票'`，
`Rows = [[stocNo, stocName, shares, weight], ...]`（4 欄）
""",
        'quirks': """\
- FundID 直接用上市代號（不需轉換）
- 偶發 HTTP 500（網路 transient），retry 1 次即可
- stock_name 是全名「台灣積體電路製造」非簡稱「台積電」
""",
        'triage': """\
1. HTTP 500 → 一次性，重跑
2. 'no stock table in response' → API schema 變了，看完整 response
""",
    },
    'allianz': {
        'display': '安聯投信 (etf.allianzgi.com.tw)',
        'api': """\
雙步驟：先拿 AntiForgery 的 XSRF cookie，再帶 X-XSRF-TOKEN header POST：

```http
GET https://etf.allianzgi.com.tw/webapi/api/AntiForgery/GetAntiForgeryToken
  → 拿 cookie X-XSRF-TOKEN

POST https://etf.allianzgi.com.tw/webapi/api/Fund/GetFundAssets
Content-Type: application/json
X-XSRF-TOKEN: <cookie value>

{{"FundID":"{fund_code}"}}
```

回應 `Entries.Data.Table[*]` 找 `TableTitle.startswith('股票')`，
row 是 `[序號, stocNo, stocName, shares, weight%]`（5 欄含序號）
""",
        'quirks': """\
- **FundID 是內部代號 `{fund_code}`，不等於上市代號**
- 用 requests.Session 維護 cookie，X-XSRF-TOKEN 同時放 cookie + header（雙重提交防 CSRF）
""",
        'triage': """\
1. HTTP 400 → 沒帶 X-XSRF-TOKEN header
2. 'no X-XSRF-TOKEN cookie' → AntiForgery endpoint 改名/路徑變
""",
    },
    'fsitc': {
        'display': '第一金投信 (fsitc.com.tw)',
        'api': """\
```http
POST https://www.fsitc.com.tw/WebAPI.aspx/Get_hd
Content-Type: application/json

{{ 'pStrFundID':'{fund_code}','pStrDate':''}}
```

**注意 body 是字面 string（不是標準 JSON）**，帶引號和空格。

回應：`{{"d": "<JSON-encoded string>"}}` ─ 需 `json.loads(outer['d'])` 解第二層。
inner row：`{{fundid, sdate, group, A=stock_id, B=name, C=weight%, D=shares}}`
""",
        'quirks': """\
- body 開頭有空格、用單引號 — 不是 valid JSON，但 server 接受
- response 雙層 json encode，先 r.json() 拿 outer，再 json.loads(outer['d'])
""",
        'triage': """\
1. status 非 200 → API 變了
2. KeyError 'd' → response 結構變了，看 raw text
""",
    },
    'jpm': {
        'display': '摩根投信 (am.jpmorgan.com/tw)',
        'api': """\
```http
GET https://am.jpmorgan.com/FundsMarketingHandler/product-data
    ?cusip={fund_code}
    &country=tw&role=twetf&language=zh
```

持股藏在 `fundData[0].holdings.pcfEquityHoldings.data[*]`，
欄位：`securityTicker, securityDescription, shares, marketValuePercent, marketValue, navDate`
""",
        'quirks': """\
- ISIN 格式 `TW00000` + ETF 5 字 + Luhn check digit
- 持美股的 ETF（如 00989A），securityTicker 是英文（GOOG / INTC）
- 持台股的 ETF（如 00401A），securityTicker 是數字（2330）
""",
        'triage': """\
1. 'no fundData' → ISIN 不對；用 brute-force `TW00000<ETF 5碼><0-9A-Z>` 試 check digit
2. 'no pcfEquityHoldings.data' → effectiveDate 可能為 null（剛上市），check `holdings_block`
""",
    },
    'tsit': {
        'display': '台新投信 (tsit.com.tw)',
        'api': """\
```http
GET https://www.tsit.com.tw/ETF/Home/Pcf?id={fund_code}
```

整頁 SSR，用 BeautifulSoup 找 4-cell `<tr>`：
`<td>2330 TT</td><td>台積電</td><td>22,000</td><td>7.7%</td>`
""",
        'quirks': """\
- ticker 是 `"2330 TT"` / `"GOOGL US"` 帶市場後綴（TT/US/HK/JP/UK/GR/FP/CN），需 regex 拆掉
- 全球龍頭型 ETF（00986A）有大量美股
""",
        'triage': """\
1. 'no holdings row parsed' → HTML 結構變了，dump tr.text 對齊
2. status 非 200 → URL 變了
""",
    },
    'mega': {
        'display': '兆豐投信 (megafunds.com.tw)',
        'api': """\
```http
GET https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id={fund_code}
```

ASPX 頁面 SSR，持股 row 是 4 個 `<div class="fund-content">` 在 `<div class="fund-info content-list-1">` 內：
順序：stock_id, name, shares, weight%
""",
        'quirks': """\
- 完全無 XHR、整頁 SSR
- 資料日期看「資料來源：兆豐投信，YYYY/MM/DD」字串
""",
        'triage': """\
1. 'no holdings row parsed' → CSS class 變了，看 HTML 結構
""",
    },
    'cathay': {
        'display': '國泰投信 (cathaysite.com.tw)',
        'api': """\
**主站 cathaysite.com.tw 被 Akamai 擋 headless；但 API 子網 cwapi.cathaysite.com.tw 直接打就過。**

```http
GET https://cwapi.cathaysite.com.tw/api/ETF/GetETFDetailStockList
    ?FundCode={fund_code}
    &SearchDate=2026-05-15
```

回應 `result = [{{stockCode, stockName, volumn, weights}}, ...]`
""",
        'quirks': """\
- FundCode 是內部 2-字母代碼（如 `{fund_code}`），不是 ETF 上市代號
- **週末 / 假日無資料 → fetcher fallback 前 7 天找最近交易日**
- 個股 name 含全形空格（"信  驊"）需 replace 處理
- 主站被 Akamai 擋；用 stealth 模式（`Stealth().use_sync(playwright)`）可繞，但 cwapi 直接打更快
""",
        'triage': """\
1. 'empty result for last 7 days' → API 路徑變或 FundCode 不對
2. ct 非 json → 被防火牆擋，加 Origin/Referer
""",
    },
    'ctbc': {
        'display': '中信投信 (ctbcinvestments.com.tw)',
        'api': """\
雙步驟：先 AuthToken 拿 token，再帶 URL param 呼叫 Buyback：

```http
POST https://www.ctbcinvestments.com.tw/API/home/AuthToken?token=www.ctbcinvestments.com
  body: {{}}
  → Data.token

POST https://www.ctbcinvestments.com.tw/API/etf/Buyback?token=<url-encoded token>
Content-Type: application/json

{{"FID":"{fund_code}","StartDate":"2026-05-15"}}
```

回應持股在 `Data.Detail[*].Data`（filter `Code == "STOCK"`），
欄位前綴底線：`code_, name_, qty_, weights_, amount_, price_`
""",
        'quirks': """\
- **body schema 是 `FID + StartDate`**（不是直覺的 `CNO / Date` — 從 Vite chunk 反查到的）
- FID `{fund_code}` 是內部代號，CNO 才是 ETF 上市公司編號
- code_ 可能是 `"TSLA US"` 等含市場後綴，需 regex 拆掉
- **週末 / 假日無資料 → fetcher fallback 前 7 天**
""",
        'triage': """\
1. `SqlDateTime 溢位` → body schema 錯，用 `FID + StartDate`（不是 CNO/Date）
2. 'no data in last 7 days' → token 過期 / FID 改了
""",
    },
    'fhtrust': {
        'display': '復華投信 (fhtrust.com.tw)',
        'api': """\
```http
GET https://www.fhtrust.com.tw/api/assets?fundID={fund_code}&qDate=2026/05/15
```

**個股藏在 `result[0].detail` 鍵（不是 `result[0].result`！）**：
`detail = [{{ftype, stockid, stockname, qshare, mvalue, price, prate_addaccint, ...}}]`
""",
        'quirks': """\
- **`result[0].result` 是 asset-class 匯總（只 3 行 — 股票/現金/應付），曾經錯把它當持股**
- 個股在 `detail`，過濾 `ftype == '股票'`
- 國際金融型（00998A）持歐美股，stockid 含 2-letter 國家碼如 `"LGEN LN"` / `"ABN NA"`
- 週末 / 假日無資料 → fetcher fallback 前 7 天
""",
        'triage': """\
1. 'no stock rows in detail' → ftype 篩選錯，或 stockid 含國際後綴沒處理
2. 'no detail in last 7 days' → API 路徑變或 fundID 不對
""",
    },
}


def render(etf_id: str, etf_name: str, issuer: str, fund_code: str, fetcher_module: str,
           holdings_n: int | None, aum_b: float | None, sample_top: list) -> str:
    """Render one SKILL.md."""
    tpl = ISSUER_TEMPLATES[fetcher_module]
    issuer_display = tpl['display']
    api = tpl['api'].format(fund_code=fund_code, etf_id=etf_id)
    quirks = tpl['quirks'].format(fund_code=fund_code, etf_id=etf_id)
    triage = tpl['triage'].format(fund_code=fund_code, etf_id=etf_id)

    aum_str = f'{aum_b:,.1f} B TWD' if aum_b else '<NA>'
    n_str = f'{holdings_n} 檔' if holdings_n else '<NA>'

    top_str = '\n'.join(
        f'    {h[0]} {h[1]:8s}  shares={h[2]:>10,}  weight={h[3]}%'
        for h in sample_top[:3]
    ) if sample_top else '    <NA>'

    return f'''---
name: etf-{etf_id}
description: 抓取或除錯主動式 ETF {etf_id}（{etf_name}，發行：{issuer}）的每日 PCF 持股資料。當使用者要重新抓 {etf_id}、檢查最新持股、確認 fetcher 是否正常、修復 {etf_id} 抓取錯誤、或回填某天的 {etf_id} 資料時觸發。
---

# ETF {etf_id} — {etf_name}

## 基本資料

| 欄位 | 值 |
|---|---|
| ETF 代碼 | {etf_id} |
| 名稱 | {etf_name} |
| 發行投信 | {issuer_display} |
| 上市 | TWSE |
| 內部 Fund Code | `{fund_code}` |
| Fetcher Module | `fetchers/{fetcher_module}.py` |
| 持股檔數 | {n_str} |
| 規模 (AUM) | {aum_str} |

## 抓取方式（一行）

```bash
cd ~/Documents/active-etf-tracker && \\
  .venv/bin/python -c "from datetime import date; from fetchers import fetch; r = fetch('{etf_id}', date.today()); print(f'ok={{r.ok}}  n={{len(r.holdings)}}  err={{r.error}}'); [print(h) for h in r.holdings[:5]]"
```

## API 細節

{api}

## 已知 quirks

{quirks}

## 入庫 + 更新報告

跑全部 22 檔並重新生成靜態網站：
```bash
cd ~/Documents/active-etf-tracker && \\
  .venv/bin/python scripts/run_daily.py && \\
  .venv/bin/python scripts/build_site.py
```

回填某天：
```bash
.venv/bin/python scripts/run_daily.py 2026-05-16
```

## 失敗排查順序

{triage}

## 最新樣本（生成 SKILL 當下）

```
{top_str}
```

## 相關檔案

- Fetcher：`~/Documents/active-etf-tracker/fetchers/{fetcher_module}.py`
- DB：`~/Documents/active-etf-tracker/data/holdings.db`（`holdings` 表 WHERE etf_id='{etf_id}'）
- 主技術手冊：`~/Documents/active-etf-tracker/notes/FETCHER_GUIDE.md`
'''


def main():
    con = sqlite3.connect(DB)
    rows = con.execute('''
        SELECT m.etf_id, m.etf_name, m.issuer, m.fund_code, m.fetcher_module,
               s.holdings_n, s.total_assets/1e9 AS aum_b
        FROM etf_meta m
        LEFT JOIN fund_snapshot s ON s.etf_id = m.etf_id
            AND s.date = (SELECT MAX(date) FROM fund_snapshot WHERE etf_id = m.etf_id)
        WHERE m.fetcher_module IS NOT NULL AND m.fetcher_module != ''
        ORDER BY m.etf_id
    ''').fetchall()

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    n_made = 0
    for etf_id, name, issuer, fund_code, mod, hn, aum in rows:
        # 跳過 sample 已存在的
        skill_dir = SKILLS_DIR / f'etf-{etf_id}'
        skill_dir.mkdir(parents=True, exist_ok=True)
        target = skill_dir / 'SKILL.md'

        # 抓 top 3 持股
        top = con.execute('''
            SELECT stock_id, stock_name, shares, weight FROM holdings
            WHERE etf_id=? AND date=(SELECT MAX(date) FROM holdings WHERE etf_id=?)
            ORDER BY weight DESC LIMIT 3
        ''', (etf_id, etf_id)).fetchall()

        content = render(etf_id, name, issuer, fund_code, mod, hn, aum, top)
        target.write_text(content, encoding='utf-8')
        n_made += 1
        print(f'  → {target}')

    con.close()
    print(f'\n{n_made} ETF skills written to {SKILLS_DIR}')


if __name__ == '__main__':
    main()
