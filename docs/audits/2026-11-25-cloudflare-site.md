# 2026-11-25：最新報告切換與 Cloudflare 網站上線驗收

[功能說明](../LATEST_SITE.md) · [設定指南](../CLOUDFLARE_SETUP.md)

本次已上線至 [Cloudflare 主站](https://pmot-independent-trigger.cjw-9223233.workers.dev/) 與 [GitHub Pages](https://cjw9223233.github.io/PMOT/)。以下時間均為 Asia/Taipei；這是當次實測，未代表未來排程必然準時。

## 實際部署證據

| 項目 | 驗收結果 |
| --- | --- |
| 程式變更 | [PR #10](https://github.com/cjw9223233/PMOT/pull/10)；合併前 [CI](https://github.com/cjw9223233/PMOT/actions/runs/45528136541) 通過 |
| 正式雙站部署 | [Run 45528345795](https://github.com/cjw9223233/PMOT/actions/runs/45528345795)，build / deploy 均 success |
| 使用行情快照 | `data/2026-11-25_080044.html`，產出時間 08:00:44；改版部署略過新行情查詢，歷史快照未覆寫 |
| Pages 部署步驟完成 | 09:48:21 |
| Cloudflare 部署步驟完成 | 09:48:28；金鑰權限可完成 Worker、Static Assets 及 Cron 部署 |
| 公開內容驗證 | Pages 09:48:28.769、Cloudflare 09:48:29.803，各 8 個檔案與固定 commit 的 SHA-256 相符 |
| 雙站成功收據 | 09:48:30，`.pmot/deployment.json` 的兩個 targets 皆 verified |
| 重複執行 | [Run 45528848997](https://github.com/cjw9223233/PMOT/actions/runs/45528848997) success；決策 skip，deploy skipped，未重抓行情 |

8 個檔案包含首頁、JS、CSS、報告清單、部署 metadata、最新內容片段、最新獨立報告及最舊獨立報告。GitHub runner 直接以公開 HTTPS 逐一比對，並驗證 health 及未授權 check；不是僅看 Actions 綠燈判定成功。

## 行為與設定

- 48 項 Python、29 項 Node / workerd 測試通過；Wrangler dry-run 成功。
- 舊首頁實際載入最新內容、60 秒與前景更新、跨日切換、歷史網址保持、回到最新、離線保留內容及慢請求競態都有自動測試。
- 本機 Edge 實際版面檢查：桌面 1440px、手機 390px 無橫向溢出，章節錨點無缺漏，17 筆歷史選單可切換。
- 正式 Cloudflare `/health` 回應 200 / `ok=true`；`data/reports.json` 回應 200 / `Cache-Control: no-store`。
- Cloudflare 原有 `GITHUB_TOKEN`、`CHECK_TOKEN` 秘密名稱仍在；受保護的 POST `/check` 成功讀取 GitHub 與兩站版本，回報 `state=delivered`，run ID 與本次部署相符。
- 原 Cron `0,10,30,45,55 0 * * *` 保留；GitHub 台北 08:00、08:17、08:37 排程保留。交易日查核、重試與歷史選擇皆保留。
- 新手設定只需 GitHub Repository secret `CLOUDFLARE_API_TOKEN` 與 variable `CLOUDFLARE_ACCOUNT_ID`；本次均已設定，未重設 Worker runtime 秘密。

## 時效與限制

今日原報告由 Cloudflare 於 08:00:24.439 請求，[Run 45514609439](https://github.com/cjw9223233/PMOT/actions/runs/45514609439) 於 **08:01:09** 完成原 Pages 交付，早於 09:00。本次是 09:48 的網站改版及首次雙站發布；當次收據如實標示 late，不將 08:00:44 的行情產出時間冒充部署時間。

因此本次部署後的受保護 `/check` 回應 HTTP 503，JSON 為 `state=delivered`、`before_open=false`；503 表示本次部署未達開盤前時效，不是網站部署失敗。下一交易日實際 Cron 觸發及雙站開盤前交付仍須由未來執行紀錄驗證。

這台電腦全新無頭 Edge profile 連正式網址時顯示 `NET::ERR_CERT_AUTHORITY_INVALID`，故未將正式網址的瀏覽器互動驗收宣稱通過，也未略過憑證驗證。公開 HTTPS 由 GitHub runner 與本機 PowerShell 驗證成功；瀏覽器版面與互動使用本機同版網站驗證。此環境信任鏈限制與正式部署驗證分別記錄。
