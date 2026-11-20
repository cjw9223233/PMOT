# 2026-11-20 Cloudflare 初次驗收：尚未到首次排程時槽

[回 README](../../README.md) · [上線紀錄](2026-11-20-cloudflare-activation.md) · [設定與驗收步驟](../CLOUDFLARE_SETUP.md)

**結論：設定、GitHub 讀取及線上交付查核通過；自動喚醒、上線後休市略過與交易日 09:00 前交付，均尚未有真實樣本可驗收。沒有發現需修改程式的異常。**

本次查核開始時間為 **2026-11-20 11:56:59 +08:00**。Cloudflare 當日 **10:03:26** 才啟用，五個每日時槽（08:00、08:10、08:30、08:45、08:55）皆已過。因此從啟用至本次查核，應發生的 Cron 次數是 **0**，不能把空紀錄判定為漏跑，也不能把上線前的人工執行當成自動成功。

## 實際資料與驗收判定

| 驗收項目 | 本次證據 | 判定 |
| --- | --- | --- |
| Cron 設定是否仍存在 | Cloudflare API 讀回 `0,10,30,45,55 0 * * *`；建立、修改時間均為 `2026-11-20T02:03:26.28595Z` | 通過，未被刪除或改時槽 |
| Runtime 金鑰是否存在 | 僅查名稱，`CHECK_TOKEN`、`GITHUB_TOKEN` 皆存在 | 通過；未讀回或保存值 |
| 實際 Cloudflare Cron 紀錄 | GraphQL 專用 `workersInvocationsScheduled` 查詢回 `[]`，`errors=null` | 應到期 0、觀測 0；尚非自動執行驗收 |
| 啟用後 GitHub 報告工作 | 查每日 workflow 最近 100 次，建立時間在 `2026-11-20T02:03:26Z` 之後者為 0 | 與尚無到期 Cron 一致 |
| 新 GitHub token 讀取能力 | 受保護 `/check` 成功核對 GitHub 查核紀錄、清單、收據及 run | 通過 |
| 公開網站交付核對 | `/check` 為 `state=delivered`，對應實際 run `44657078895` | 通過，僅證明目前版本已交付 |
| 逾時分類是否正確 | HTTP 503、`before_open=false`，完成時間 09:55:54 | 通過，沒有把部署成功誤標準時 |
| Worker 實際喚醒 Actions | 尚無 `trigger_source=cloudflare` 的上線後工作樣本 | 待首次真實 Cron；Actions write 亦尚待此路徑驗證 |
| 上線後休市日正確略過 | 尚未經過任何上線後的早晨／休市時槽 | 未驗收；不拿 11/14、11/15 的舊 GitHub 排程替代 |
| 上線後交易日 09:00 前完成 | 尚未經過任何上線後的交易日早晨 | 未驗收；無法計算準時率 |

Cron 歷史採專用 scheduled dataset，而非一般 HTTP 請求數；人工開啟 `/health`、呼叫 `/check` 不算 Cron。

## 今日唯一相關交付，為人工且發生在啟用前

| 時點（台北） | 事件 |
| --- | --- |
| 09:55:20 | [Actions 44657078895](https://github.com/cjw9223233/PMOT/actions/runs/44657078895) 由 `workflow_dispatch` 建立 |
| 09:55:36 | 報告產出 |
| 09:55:54 | 部署確認；逾 09:00 共 55 分 54 秒 |
| 10:03:26 | Cloudflare Cron 才啟用 |
| 11:56:59 起 | 本次唯讀查核，沒有新增報告或觸發 Actions |

`.pmot/check.json` 與成功收據均標示 `trigger_source=manual`。因此這次人工交付不能證明 Cloudflare 自動喚醒成功，也不能用它評估 Cloudflare 的延遲。

受保護查核回應：

```json
{
  "state": "delivered",
  "day": "2026-11-20",
  "run_id": "44657078895",
  "completed_at": "2026-11-20T09:55:54+08:00",
  "before_open": false
}
```

HTTP 503 在此代表「已交付但未達開盤前時效」，不是服務沒有啟用或 GitHub token 失效。

## 維護動作與限制

管理端查詢一開始遇到 OAuth 到期（到期時間 `2026-11-20T02:50:06.478Z`），已沿用現有 refresh 流程更新 Wrangler 管理登入後重查成功。這是控制台查詢憑證，不是 Worker 的長效 `GITHUB_TOKEN`；未修改 Runtime Secret、程式、排程或任何報價，也未要求重新登入或新增金鑰。

本次沒有發現需修改應用程式的實際異常。保留 GitHub 08:00、08:17、08:37 備援；沒有為了製造成功樣本而提前喚醒、改時鐘、臨時改 Cron 或把人工測試改標 Cloudflare。

## 下一次真實驗收要核對什麼？

下一個預定時槽為 **2026-11-21 08:00（Asia/Taipei）**；這是預定時間，不保證平台已執行。11/21、11/22 是週末，仍以原 Python 官方交易日查核結果為準。

1. Cloudflare Cron Events／Workers Logs：找實際 `scheduled_at`、`checked_at`、`requested` 或 `closed`，核對觸發延遲及錯誤。
2. GitHub 對應 run：來源應為 `workflow_dispatch`，timing／check 內應有 `trigger_source=cloudflare` 與 `external_requested_at`。只看到 `workflow_dispatch` 不足以區分人工或 Worker。
3. 若確認休市：應保存當日 `market_state=closed`、`decision=skip`；不產生該日新報告，後續 Worker 查核應顯示 `closed`。
4. 若正常交易：核對當日首次報告與成功收據，再確認公開網站版本一致；部署確認嚴格早於 09:00:00 才算準時。
5. 補跑需避免重複產報告；另將後續改版部署時間與當日首次交付區分，累積至少五個正常交易日後才計算準時率。

本文件是一份當下的驗收快照，沒有排定 Codex 自動回來查核，也沒有宣稱未來時槽已通過。使用者可在實際時槽後交辦續查，或依設定指南自行查紀錄。

## 來源

- Cloudflare 官方 API：Worker schedules、Secret **名稱**、GraphQL `workersInvocationsScheduled` 與受保護 `/check`；不在文件中保存授權值。
- GitHub API：每日 workflow run 清單，及儲存庫 `.pmot/check.json`、`.pmot/deployment.json`、報告 JSON。
- [Cloudflare Cron 官方說明](https://developers.cloudflare.com/workers/configuration/cron-triggers/)：UTC、傳播與 Cron Events；未把傳播期間或 HTTP 存取當作真實 Cron 成功。
