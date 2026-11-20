# 2026-11-20 Cloudflare 獨立觸發上線紀錄

[回 README](../../README.md) · [新手設定與停用](../CLOUDFLARE_SETUP.md)

## 已完成的部署

| 項目 | 結果 |
| --- | --- |
| Worker | `pmot-independent-trigger` |
| 網址 | [pmot-independent-trigger.cjw-9223233.workers.dev](https://pmot-independent-trigger.cjw-9223233.workers.dev/health) |
| 程式與文件 | [PR #7 已合併](https://github.com/cjw9223233/PMOT/pull/7) |
| 本機與雲端驗證 | 45 項 Python、18 項 Worker 測試通過，含 workerd；官方 Wrangler dry-run 通過 |
| Runtime Secrets | 已確認名稱 `GITHUB_TOKEN`、`CHECK_TOKEN` 存在；未將值寫入文件或版本庫 |
| Cloudflare Cron | 官方 API 已設定並讀回 `0,10,30,45,55 0 * * *`，一條 UTC cron |
| 啟用時間 | Cloudflare `created_on`：2026-11-20 02:03:26 UTC，即台北 **10:03:26** |
| 原有 GitHub 備援 | 每日 08:00、08:17、08:37（Asia/Taipei）保留 |

Cloudflare 三個觸發時槽為台北 08:00、08:10、08:30；08:45、08:55 僅查核。沒有啟用付費功能、KV、D1 或訊息發送服務。

本機使用者完成 Wrangler OAuth 與專用 GitHub token Secret 設定。代理憑證使代理執行環境的 Node 仍無法連線，因此本次沿用該登入，以系統驗證 HTTPS 的官方 Cloudflare API 上傳同一份原始碼、設定查核 Secret、啟用並讀回排程，沒有關閉 TLS 驗證。日後可依設定文件使用網路正常的 Wrangler 或 GitHub 人工部署 workflow 維護。

## 線上實測

- `GET /health`：HTTP 200；只證明 HTTP 程式可回應。
- 未授權 `POST /check`：HTTP 401；唯讀端點保護有效。
- 帶正確查核憑證的 `POST /check`：HTTP 503，內容如下。這是逾時分類，不是 token 失效。

```json
{
  "state": "delivered",
  "day": "2026-11-20",
  "run_id": "44657078895",
  "completed_at": "2026-11-20T09:55:54+08:00",
  "before_open": false
}
```

Worker 已以新 GitHub token 讀取查核紀錄、最新報告清單、成功收據與 run，並核對公開網站版本。它如實指出今天已交付但逾 09:00，而不是因部署成功就回報準時。對應 [Actions 紀錄](https://github.com/cjw9223233/PMOT/actions/runs/44657078895)為本對話人工驗證，不是 Cloudflare 自動觸發。

Actions 新增的 `.pmot/check.json` 也已實際保存當日 `market_state=open`、`decision=generate` 與 `trigger_source=manual`，沒有偽造 Cloudflare 來源。

## 尚待真實時槽驗收

啟用時已過當日五個時槽。下一次預定執行是 **2026-11-21 08:00（Asia/Taipei）**，仍須考量平台傳播與執行延遲。尚不能宣稱真實 Cron 已執行、Actions write 權限已透過真實 dispatch 驗證，或已改善五個交易日的準時率。

下一次應核對 Cloudflare `requested` 日誌、GitHub `trigger_source=cloudflare`、`external_requested_at` 及交易日 check。休市應結束於 `closed` 且不新增報告；正常交易日應等到收據與公開網站相符才算交付，再觀察後續補跑不重複產報告。

本次沒有建立額外本機排程或 Codex 背景監控；08:45／08:55 的警示仍是 Worker 日誌／Cron 失敗事件，不會自動發送 email 或聊天訊息。
