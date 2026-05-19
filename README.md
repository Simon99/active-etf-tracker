# active-etf-tracker

台股主動式 ETF 每日持股追蹤 — **靜態網站發布站**。

🌐 **網站：https://simon99.github.io/active-etf-tracker/**

---

## 這個 repo 裝什麼

只有 `docs/` — GitHub Pages 服務的靜態 HTML。

- 22 檔主動式 ETF daily 持股快照
- 持股異動 / 持股重疊 / 個股反查 / 同步加碼 / 雷達 / 技術線型

## 程式碼在哪？

**私有 repo**（含 fetchers、scripts、資料庫、daily workflow）。

公開 repo 只當 GitHub Pages 的 deploy target — 每天台灣 17:30 / 20:00 / 隔天 05:00，
私有 repo 的 GitHub Actions 跑完後會自動 push 新的 `docs/` 到這裡。

## 自動更新狀態

每頁 nav 右側 ● chip 顯示「上次更新 N 分鐘前」：
- 🟢 < 12 小時 — 正常
- 🟡 12 小時 - 3 天 — 可能漏了一次 cron
- 🔴 > 3 天 — cron 可能掛了
