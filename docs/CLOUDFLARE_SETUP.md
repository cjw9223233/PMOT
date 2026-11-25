# Cloudflare 免費獨立觸發：新手設定與驗收

[回 README](../README.md) · [自動化流程](AUTOMATION.md) · [GitHub 交付機制](DELIVERY.md)

Cloudflare Worker 負責喚醒及查核，行情、交易日判斷、HTML 與 Pages 部署仍由 GitHub Actions／Python 執行。GitHub 原有 08:00、08:17、08:37 備援全部保留；沒有遷移網站、啟用付費方案或常駐本機程式。**檔案合併不等於 Worker 已上線**，須完成登入、設定 Secret、部署及下列驗收。

原專案已於 2026-11-20 完成部署與 Cron 啟用，實測與待驗收項目見[上線紀錄](audits/2026-11-20-cloudflare-activation.md)。以下步驟供重建、更新或其他帳號使用；不必重設已存在的金鑰。

最新查核快照：[2026-11-20 初次驗收](audits/2026-11-20-cloudflare-acceptance.md)。記錄「尚未到首個時槽」與真正的漏跑不同，查核時應先算啟用後應到期的時槽數。

## 1. 先看流程

```mermaid
flowchart TD
    CF[Cloudflare UTC 排程] --> READ[讀 GitHub 官方查核、報告清單、成功收據與 run]
    READ -->|今日明確休市| CLOSED[略過，不宣稱交付失敗]
    READ -->|有相符成功收據| SITE[確認公開網站的版本與收據相符]
    SITE -->|相符| OK[交付已確認，另列是否在 09:00 前]
    SITE -->|不相符或無法讀取| UNKNOWN[網站尚未確認，不假裝成功]
    READ -->|工作仍在執行或排隊| WAIT[不重複喚醒，超過 20 分鐘標示 stalled]
    READ -->|需要補跑且在觸發時槽| POST[GitHub workflow_dispatch API]
    POST --> GH[原有 Actions 查交易日、產報告或重試部署]
    GH --> CHECK[保存 .pmot/check.json 與成功收據]
    CHECK --> READ
```

Worker 不自行用星期幾推論台股休市。Actions 的 `prepare` 成功查核後保存 `market_state=open/closed`；無法確認則保存 `unknown` 並使原工作失敗。程式更新的 push 不查交易日，也不會蓋掉已有查核紀錄。

## 2. 需要的帳號與工具

- GitHub：能管理 `cjw9223233/PMOT` 的帳號。
- Cloudflare：使用 Workers Free 即可，無須自有網域。
- 本機：Git、Node.js 22 以上、npm。原 Python 測試仍依專案快速上手設定。

在 PowerShell 進入專案：

```powershell
Set-Location D:\Downloads\PMOT\cloudflare
npm ci
npm test
npm run dry-run
```

`npm test` 使用合成回應，不連真實 GitHub、不部署。`dry-run` 由官方 Wrangler 檢查並打包 Worker，不會建立雲端服務。若 npm 出現憑證錯誤，先修復本機信任憑證或使用乾淨環境／CI；不要關閉 TLS 驗證。

## 3. 建立專用 GitHub 金鑰

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token。

| 設定 | 值 |
| --- | --- |
| Resource owner | `cjw9223233` |
| Repository access | Only select repositories → `PMOT` |
| Repository permissions | **Actions: Read and write**、**Contents: Read-only**（另有自動必要的 Metadata read） |
| Expiration | 自行選擇到期日並記錄更新提醒 |

Actions write 用於喚醒及讀 run；Contents read 用於讀取查核紀錄、清單與收據。Worker 不需要 Contents write、Pages write 或 Cloudflare 管理金鑰。此權限仍可操作 PMOT 的 Actions，應視同密碼保管。

不要使用本機 `gh` 的廣泛 OAuth token，也不要把金鑰貼進聊天、README、`wrangler.jsonc` 或 git。下面的互動提示會讓你直接輸入 Secret。

## 4. 每日雙站部署：設定 GitHub Actions 金鑰

報告現在由同一個每日 workflow 發布到 Cloudflare Worker 靜態網站與 GitHub Pages。只在兩站公開內容驗證通過後寫成功收據。設定一次後，每日不需要本機登入。

1. 開啟 [Cloudflare 個人 API Tokens](https://dash.cloudflare.com/profile/api-tokens) → Create Token。
2. 在 API token templates 找 **Edit Cloudflare Workers** → Use template。找不到時可 Create Custom Token，設定 `Account → Workers Scripts → Edit`、`Account → Account Settings → Read`。
3. Token 名稱可填 `PMOT GitHub Deploy`。Account Resources 選 `Include → Specific account`，僅選 PMOT 所在帳號；Client IP Filtering 留空，避免 GitHub runner IP 變動被擋。記錄金鑰到期日。
4. Continue to summary → Create Token，將值直接複製到 [PMOT Actions Secrets](https://github.com/cjw9223233/PMOT/settings/secrets/actions) → New repository secret，名稱為 `CLOUDFLARE_API_TOKEN`。
5. Repository variables 應有 `CLOUDFLARE_ACCOUNT_ID`，填 Cloudflare Account ID，不是 Zone ID；原專案已設定。

| 存放位置 | 名稱 | 用途 |
| --- | --- | --- |
| GitHub Repository secret | `CLOUDFLARE_API_TOKEN` | 發布 Worker 程式及靜態資產的 Cloudflare token |
| GitHub Repository variable | `CLOUDFLARE_ACCOUNT_ID` | 發布到哪個 Cloudflare account |
| Cloudflare Worker Secret | `GITHUB_TOKEN` | Worker 日常喚醒、讀 GitHub 紀錄；保留原值 |
| Cloudflare Worker Secret | `CHECK_TOKEN` | 保護 `/check`；保留原值 |

兩組用途不同：不要把 GitHub token 當作 Cloudflare 部署 token。每日發布會保留既有 Worker runtime Secrets，不會要求把它們另複製至 GitHub，也不會重新產生查核密碼。

需要人工重建時，在 Actions 執行 `Deploy independent Cloudflare trigger`。它現在只送出 `rebuild_only=true` 的每日發布請求，**請繼續追蹤 Daily market report and GitHub Pages 的結果**；請求受理不等於網站部署成功。人工重建不查新行情，仍用既有快照。原 GitHub 三時槽保留。

## 5. 本機網路正常時：登入並設定 Secret（替代方式）

```powershell
# 此步會開啟 Cloudflare 瀏覽器授權；確認選擇你自己的 Free 帳號。
npx wrangler login
npm run whoami

# 若 Worker 尚不存在，依提示同意建立 pmot-independent-trigger。
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put CHECK_TOKEN
```

- `GITHUB_TOKEN`：上一步新建的 GitHub fine-grained token。
- `CHECK_TOKEN`：另選一個長且隨機的密碼，只用於保護 `/check` 唯讀查核；不要與 GitHub token 相同。

只有 Secret 值需要保密；Worker 程式、帳號名稱及排程可公開。若帳號有多個 Cloudflare account，先核對 `whoami`，必要時於本機環境設定正確的 `CLOUDFLARE_ACCOUNT_ID`。不要隨意啟用付費 Workers。

## 5A. 靜態網站與共用排程說明

先確認 GitHub main 已有本次 `workflow_dispatch` inputs 及 checkpoint 步驟，再執行：

```powershell
npm run deploy
```

部署完成會顯示 `https://pmot-independent-trigger.<你的子網域>.workers.dev`。原專案首頁為 [Cloudflare 報告網站](https://pmot-independent-trigger.cjw-9223233.workers.dev/)，GitHub Pages 仍保留；詳細模式與雙站發布見 [最新報告網站](LATEST_SITE.md)。本機直接 deploy 僅適合除錯，正式更新請用每日雙站流程，否則不會產生兩站驗證收據。

| 台北時間 | UTC | 行為 |
| --- | --- | --- |
| 08:00 | 00:00 | 查狀態，需要時喚醒 Actions |
| 08:10 | 00:10 | 條件補跑，已有收據或執行中就不排隊 |
| 08:30 | 00:30 | 條件補跑 |
| 08:45 | 00:45 | 只查核；尚未確認時記錄 `alert=true` |
| 08:55 | 00:55 | 只查核；尚未確認或逾時，讓 Cron invocation 失敗供看板辨識 |

設定集中於 [wrangler.jsonc](../cloudflare/wrangler.jsonc)，一條 cron 表達式包含五個分鐘值。Cloudflare Cron 使用 UTC；新建或修改可能需要最多約 15 分鐘傳播，不能剛部署就宣稱排程已驗收。所有時槽都可在休市日喚醒，由原 Python 官方查核決定略過。

Worker 若收到超過 15 分鐘的舊時槽或已跨台北日期，不會再用該時槽觸發。若看到執行中工作超過 20 分鐘，標示 `stalled` 而不持續堆積請求。GET 暫時失敗最多再試一次；POST 結果不明不立即重送，交由下一時槽讀 run 再判斷。兩個平台同時喚醒仍可能產生額外 run，GitHub 原有 concurrency 與快照／收據比對負責避免重複產報告。

## 6. 人工唯讀查核

`GET /health` 只證明 HTTP 程式可回應，不表示 Secret 正確、排程已生效或報告已交付。真正查核使用受保護的 `POST /check`；沒有公開的 HTTP 觸發入口。

```powershell
$workerUrl = 'https://pmot-independent-trigger.你的子網域.workers.dev'
$checkSecret = Read-Host '輸入 CHECK_TOKEN' -AsSecureString
$credential = [pscredential]::new('check', $checkSecret)
try {
    $headers = @{ Authorization = 'Bearer ' + $credential.GetNetworkCredential().Password }
    Invoke-RestMethod -Uri "$workerUrl/check" -Method Post -Headers $headers
} finally {
    Remove-Variable headers, credential, checkSecret -ErrorAction SilentlyContinue
}
```

此入口唯讀，不能用來測試 dispatch。需要即時測試 GitHub 真實流程，可從 GitHub Actions 手動 Run workflow；測試 Cloudflare 真正 Cron → dispatch 則等待下一時槽並看記錄。不要公開貼出任何授權 header。

| state | 含義與處理 |
| --- | --- |
| `closed` | 今日 Python 已明確確認休市；不需報告 |
| `delivered` | 今日收據／清單相符，公開網站的 run、attempt 與內容指紋也相符；另看 `before_open` |
| `site_unverified` | GitHub 已確認部署，但公開網站無法確認或版本不同；不重複喚醒，須查 CDN／Pages |
| `running` | 已有工作在跑或排隊；不重複喚醒 |
| `stalled` | 工作超過 20 分鐘或時間無法確認；查 Actions，Worker 不自動取消工作 |
| `missing` | 沒有今日有效交付證據 |
| `market_unknown` | 官方交易日仍無法確認；可於補跑時槽再交給 Python 查核 |
| `requested` | GitHub 已受理喚醒，**尚非交付成功**；只出現在排程日誌 |
| `check_failed` | HTTP 查核失敗，查看 Worker Logs；不假定休市或成功 |

`/check` 對休市或開盤前交付回 200，執行中回 202，其餘含逾時回 503；PowerShell 遇 503 會顯示錯誤，可在 Cloudflare Logs 閱讀詳細分類。此設計方便未來再接外部監測，但目前沒有設定 email、Slack 或其他訊息發送。

## 7. 看日誌與驗收

```powershell
npm run tail
```

也可在 Cloudflare → Workers & Pages → Worker → Logs／Cron Events 查看。預期日誌是 JSON，包含 `scheduled_at`、`checked_at`、`state`、`alert` 及相關 run ID，不含 Secret。Actions 的 timing 與 check 紀錄會包含 `trigger_source=cloudflare`、`external_requested_at`；它們是追蹤標籤，不會繞過交易日或其他驗證。

依序確認：

1. 本機與 GitHub CI 的 Python、Worker 測試及 Wrangler dry-run 通過。
2. Cloudflare 已部署，兩個 Secret 存在，Cron 清單與上表一致。
3. 真實時槽出現 `requested`，GitHub 對應 run 標記 cloudflare；等待部署收據，不能只看 dispatch HTTP 成功。
4. `/check` 的 run ID 與 GitHub 成功收據相符，且原 Pages 網址可讀；部分行情缺漏仍需依報告狀態閱讀。
5. 後續補跑不增加相同日期的報告；休市有當日 check 紀錄而沒有新報告。
6. 至少觀察五個正常交易日，記錄外部喚醒、Actions 啟動、報告產出及當日首次部署確認。後續改版重新部署的較晚時間不可混淆當日首次交付。

免費額度下 Worker 不使用 KV、D1 或付費通知。它只做少量 API 讀取與 HTTP 請求，仍須於實際上線後查看 CPU／錯誤指標；免費額度、網路、GitHub runner 與 Pages 都不是準時交付保證。08:45／08:55 的告警目前是 Cloudflare 日誌／失敗事件，**不會自動傳送到你的信箱或本對話**。

## 8. 更新金鑰、停用與故障排除

- 金鑰到期／撤銷：重新建立同權限 token，再執行 `npx wrangler secret put GITHUB_TOKEN`。401／403 不會被當成缺報告，也不會盲目 dispatch。
- API 422：先確認 main 有 `trigger_source`、`requested_at` inputs；不要移除原 `workflow_dispatch`。
- `github_dispatch_outcome_unknown`：請求可能已受理，先看 Actions，不立即手動連按。
- 08:55 失敗事件：查 state；可能是 GitHub 排隊、官方交易日不明或網站版本未同步，不能一律歸咎市場資料。
- 暫停外部排程：把 `wrangler.jsonc` 的 `triggers.crons` 改為 `[]` 再部署。原 GitHub 備援仍在。
- 刪除 Worker 前先核對名稱／帳號，再用 Cloudflare 看板刪除；GitHub／Pages 不會因此消失。無需把 token 傳回對話。

## 官方參考

- [Cloudflare Cron 與 UTC／傳播時間](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Workers Free 限制](https://developers.cloudflare.com/workers/platform/limits/)
- [Worker Secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [GitHub workflow dispatch 與權限](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)

本文件是可重現的設定流程；實際上線狀態以部署結果與真實時槽驗收為準，不能由文件存在推定已啟用。
