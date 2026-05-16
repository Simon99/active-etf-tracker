# 主動式 ETF Fetcher 技術手冊

紀錄 22 檔主動式 ETF 的每日 PCF 抓取方式。每檔 ETF 對應到 `fetchers/<module>.py` 內的一筆 REGISTRY 項目。

## 共用機制

- 介面：`fetchers.fetch(etf_id, date)` → `FetchResult(ok, error, holdings, meta)`
- holding row schema：`date, etf_id, stock_id, stock_name, shares, weight, market_value`
- date 一律用「執行抓取當天」存入 holdings.date；issuer 自己的 PCF settle date（通常 T+2）存在 meta
- 失敗模式：HTTP 非 200、ct 非 json、解析錯、empty data → res.error 非 None
- 週末 / 假日 fallback：部分 fetcher（cathay/ctbc/fhtrust）會回溯前 7 天找最近交易日

## 11 個 issuer fetcher 摘要

| Issuer | Module | 機制 | 認證 | 假日 fallback |
|---|---|---|---|---|
| 統一 | `uni` | GET excel | 無 | 拿最新 |
| 群益 | `capital` | POST JSON | 無 | 拿最新 |
| 野村 | `nomura` | POST JSON | 無 | 拿最新 |
| 安聯 | `allianz` | POST JSON + XSRF | AntiForgery → cookie + header | 拿最新 |
| 第一金 | `fsitc` | POST JSON (body 是 string-escaped) | 無 | 拿最新 |
| 摩根 | `jpm` | GET JSON | 無 | 拿最新 |
| 台新 | `tsit` | GET HTML | 無 | 拿最新 |
| 兆豐 | `mega` | GET HTML (SSR) | 無 | 拿最新 |
| 國泰 | `cathay` | GET JSON | 無 (cwapi 子網繞 Akamai) | ✅ 7 天 |
| 中信 | `ctbc` | POST JSON | AuthToken → URL param | ✅ 7 天 |
| 復華 | `fhtrust` | GET JSON (個股藏 detail 鍵) | 無 | ✅ 7 天 |

---

## 逐檔規格（含 endpoint、body、回應結構、quirks）

### 統一投信 (`fetchers/uni.py`)
Excel 下載（民國年日期格式）。3 檔共用同一支 URL，差別 fundCode 對照：

```
00981A 主動統一台股增長  → fundCode 49YTW
00403A 主動統一升級50    → fundCode 63YTW
00988A 主動統一全球創新  → fundCode 61YTW
```

```http
GET https://www.ezmoney.com.tw/ETF/Transaction/PCFExcelNPOI
    ?fundCode=49YTW&date=115/05/16&specificDate=false
```

- 民國年 = 西元 − 1911（115 = 2026）
- Excel sheet「申購買回清單」前 ~10 行為基金 metadata，row 13 為標題「股票」，row 14 是 header（股票代號/股票名稱/股數/持股權重），row 15+ 為持股
- ezmoney 用 HTTP 200 + HTML 回 error（看 `data-content="…"`），需檢查 content-type 是不是 spreadsheet
- 注意：00988A 只持 13 檔（全球創新，分散度低）

### 群益投信 (`fetchers/capital.py`)
單一 POST endpoint，body 帶 fundId：

```
00982A 主動群益台灣強棒    → fundId 399
00992A 主動群益科技創新    → fundId 500
00997A 主動群益美國增長    → fundId 502
```

```http
POST https://www.capitalfund.com.tw/CFWeb/api/etf/buyback
Content-Type: application/json

{"fundId":"399","date":null}
```

- 回應 `data.pcf` = 基金 metadata，`data.stocks` = 持股 list
- `date1` 是 PCF settle date（T+2），`date2` 是前一交易日
- 00997A 才掛牌不久，持股只有 5 檔

### 野村投信 (`fetchers/nomura.py`)
直接用上市代號當 FundID，無需轉換：

```
00980A 主動野村臺灣優選
00985A 主動野村台灣50
00999A 主動野村臺灣高息
```

```http
POST https://www.nomurafunds.com.tw/API/ETFAPI/api/Fund/GetFundAssets
Content-Type: application/json

{"FundID":"00980A","SearchDate":null}
```

- 回應 `Entries.Data.Table` 找 `TableTitle == '股票'`，`Rows = [[stocNo, stocName, shares, weight], ...]`（4 欄）
- 偶發 HTTP 500（網路 transient），retry 即可
- stock_name 是全名「台灣積體電路製造」非簡稱「台積電」

### 安聯投信 (`fetchers/allianz.py`)
需先 GET AntiForgery token 拿 XSRF cookie，再帶 X-XSRF-TOKEN header POST：

```
00984A 安聯台灣高息成長 → FundID E0001
00993A 主動安聯台灣      → FundID E0002
```

```http
GET https://etf.allianzgi.com.tw/webapi/api/AntiForgery/GetAntiForgeryToken
  → 拿 X-XSRF-TOKEN cookie

POST https://etf.allianzgi.com.tw/webapi/api/Fund/GetFundAssets
Content-Type: application/json
X-XSRF-TOKEN: <cookie value>

{"FundID":"E0001"}
```

- FundID 是內部代號 E0001/E0002，**不等於上市代號**
- 回應 schema：`Entries.Data.Table[*]` 找 `TableTitle.startswith('股票')`，每 row 是 `[序號, stocNo, stocName, shares, weight%]`（5 欄含序號）
- 全程用 requests.Session 維護 cookie

### 第一金投信 (`fetchers/fsitc.py`)
單支 POST，body 是字面 string（不是 JSON encoded）：

```
00994A 主動第一金台股趨勢優選 → fund_id 182
```

```http
POST https://www.fsitc.com.tw/WebAPI.aspx/Get_hd
Content-Type: application/json

{ 'pStrFundID':'182','pStrDate':''}
```

- 回應 `{"d": "<string>"}`，需 `json.loads(outer['d'])` 解第二層拿 array
- 欄位是 A=代碼, B=名稱, C=權重%, D=股數

### 摩根投信 (`fetchers/jpm.py`)
ISIN-based 查詢：

```
00989A 摩根大美國領先科技 → TW00000989A5  (持美股)
00401A 摩根收益進化台灣起飛 → TW00000401A1  (持台股)
```

```http
GET https://am.jpmorgan.com/FundsMarketingHandler/product-data
    ?cusip=TW00000989A5&country=tw&role=twetf&language=zh
```

- ISIN 格式 `TW00000` + ETF 5 字 + Luhn check digit (5 / 1 等)
- 持股藏在 `fundData[0].holdings.pcfEquityHoldings.data[*]`
- 欄位：`securityTicker`（台股是數字 / 美股是英文）、`shares`、`marketValuePercent`
- 00989A 持美股，stock_id 會是英文 GOOG / INTC

### 台新投信 (`fetchers/tsit.py`)
直接 GET HTML，BeautifulSoup 解 `<tr>`：

```
00986A 主動台新全球龍頭成長
00987A 主動台新優勢成長
```

```http
GET https://www.tsit.com.tw/ETF/Home/Pcf?id=00986A
```

- 整頁 SSR，找 4-cell `<tr>`
- ticker 是 `"2330 TT"` / `"GOOGL US"` 等含市場後綴，需 regex 拆掉

### 兆豐投信 (`fetchers/mega.py`)
ASPX 頁面 SSR，BeautifulSoup 解 div 結構：

```
00996A 主動兆豐台灣豐收 → id 23
```

```http
GET https://www.megafunds.com.tw/MEGA/etf/etf_product.aspx?id=23
```

- 持股 row 是 `<div class="fund-info content-list-1">` 內 4 個 `<div class="fund-content">`
- 順序：stock_id, name, shares, weight%

### 國泰投信 (`fetchers/cathay.py`)
主站 `cathaysite.com.tw` 被 Akamai 防 bot 擋 headless；但 API 子網 `cwapi.cathaysite.com.tw` 直接打就行：

```
00400A 主動國泰動能高息 → FundCode EA
```

```http
GET https://cwapi.cathaysite.com.tw/api/ETF/GetETFDetailStockList
    ?FundCode=EA&SearchDate=2026-05-15
```

- 週末 / 假日無資料 → fetcher 回溯前 7 天找最近交易日
- 欄位：stockCode, stockName, volumn, weights
- 注意：個股 name 含全形空格（"信  驊"）會做 replace

### 中信投信 (`fetchers/ctbc.py`)
需 AuthToken 拿 token，再帶 token URL param 呼叫 Buyback：

```
00983A 主動中信ARK創新    → FID E0034
00995A 主動中信台灣卓越   → FID E0036
```

```http
POST https://www.ctbcinvestments.com.tw/API/home/AuthToken?token=www.ctbcinvestments.com
  → 拿 Data.token

POST https://www.ctbcinvestments.com.tw/API/etf/Buyback?token=<url-encoded>
Content-Type: application/json

{"FID":"E0034","StartDate":"2026-05-15"}
```

- 持股在 `Data.Detail[*].Data`（filter `Code == "STOCK"`）
- 欄位前綴底線：`code_, name_, qty_, weights_, amount_, price_`
- 週末無資料 → fallback
- 注意：body schema 是從 `assets/Buyback-*.js` Vite chunk 反查到的（不是直覺的 `CNO/Date`）
- 00983A 持美股（TSLA US, AMD US 等）

### 復華投信 (`fetchers/fhtrust.py`)
GET `/api/assets`，個股藏在 **`detail`** 鍵（不是 `result`！）：

```
00991A 復華台灣未來50主動式      → ETF23
00998A 復華全球金融股票入息主動式 → ETF24
```

```http
GET https://www.fhtrust.com.tw/api/assets?fundID=ETF23&qDate=2026/05/15
```

- 回應 `result[0].detail = [{ftype, stockid, stockname, qshare, mvalue, price, prate_addaccint, ...}]`
- `result[0].result` 是 asset-class 匯總（只 3 行 — 股票/現金/應付），曾經錯把它當持股
- 00998A 持國際金融股（LGEN LN, ABN NA 等），ticker 含 2-letter 國家碼
- 週末無資料 → fallback；今日（5/16）只 5/14 才有資料

---

## 失敗模式速查表

| 症狀 | 通常原因 | 解法 |
|---|---|---|
| HTTP 500 (野村) | API 暫時抽風 | retry 1 次 |
| `code 1010` (Cloudflare) | python urllib 預設 UA 被擋 | header 加 browser UA |
| Akamai Access Denied (國泰) | headless 被認出 | 改打 cwapi 子網，或 `Stealth().use_sync` |
| 安聯 400 | 沒帶 X-XSRF-TOKEN header | 先 GET AntiForgery |
| 中信 SqlDateTime overflow | body schema 錯（不是 CNO/Date） | 用 `FID + StartDate` |
| 復華 empty result | 看錯 key，個股在 `detail` 不是 `result` | 用 `detail` |
| 元大 maintenance redirect | 全站 08-20 維護 | 等晚上 |
| 週末空 response | issuer 假日不發新 PCF | fetcher 回溯前 7 天 |

## 增加新 ETF 流程

1. 找對的 ETF detail URL（用 `scripts/probe_issuer.py <url>` 自動探勘 XHR）
2. 看 candidate 中 score 最高的就是 PCF endpoint
3. 確認 body / response 結構，寫進 `fetchers/<issuer>.py` REGISTRY
4. 註冊到 `fetchers/__init__.py` REGISTRY.update
5. 跑 `scripts/run_daily.py` 入庫
6. `UPDATE etf_meta SET fetcher_module='<issuer>' WHERE etf_id='<new>'`
7. `scripts/build_site.py` rebuild
