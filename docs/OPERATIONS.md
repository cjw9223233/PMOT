# 維運與故障排除

[回 README](../README.md) · 前一篇：[資料規格](DATA_GUIDE.md) · 下一篇：[開發](DEVELOPMENT.md)

本手冊以具有 repo 寫入與 Actions 操作權限的維護者為對象。所有報告日期、排程與人工紀錄均以 Asia/Taipei 為準。

## 每日檢查（約 3 分鐘）

1. 開啟 [Actions](https://github.com/cjw9223233/PMOT/actions)，找到 `Daily market report and GitHub Pages` 最新一次執行。
2. 先判斷當日應為正常交易日、休市，還是官方狀態待確認。08:00 是觸發時間；不要單憑 08:00 沒有新頁面就判定故障。
3. 正常交易日查看 `build` 內的測試與更新步驟，再確認 `deploy` 是否成功。
4. 開啟[網站](https://cjw9223233.github.io/PMOT/)，核對實際產出與資料截止時間、六項章節、缺漏提示及歷史選單。
5. 若為 `partial`，逐項看來源錯誤與資料日期。不要因工作流程成功就認為所有數字都已取得。

## 先分類，再處理

| 狀態 | 執行結果／線索 | 處理方式 |
| --- | --- | --- |
| 正常略過 | 更新步驟顯示 `SKIP: ...`，`changed=false`，部署被略過 | 若與官方休市日一致，無須重跑。網站保留最近報告是預期行為。 |
| 資料部分缺漏 | `PUBLISHED ... confirmed n/9`，清單狀態為 `partial` | 檢查失敗鍵、來源日期、URL 與錯誤；其餘可確認資料仍會發布。 |
| 交易日未確認 | 更新步驟失敗，指出行事曆／公告問題 | 查官方來源、處理來源格式或公告判讀，確認後才重新執行。 |
| 市場來源全部失敗 | 更新步驟失敗，保留原報告 | 修正連線／來源後重跑；不能靠放寬數值或日期驗證產出報告。 |
| Git 提交或 push 失敗 | 報告已產生，但保存步驟失敗 | 檢查寫入權限、分支保護、main 是否有並行更新。不要 force push。 |
| 部署失敗 | build 已成功，deploy 紅燈 | 新報告可能已提交到 main，網站仍是上一版；優先修復 Pages 部署，不必先重抓行情。 |
| 網站讀取異常 | Actions 成功，但瀏覽器無法開啟或日期清單載入失敗 | 檢查網址、網路、Pages 狀態、快取，以及清單路徑對應檔案。 |

一份報告包含八組主要行情與一組 `spot` 比較資料。只剩 `spot` 成功仍會停止發布；不是任何一筆數字存在就足以產報告。

## 如何手動執行？

### 網頁方式

1. 開啟 repo → **Actions**。
2. 選擇 `Daily market report and GitHub Pages`。
3. 按 **Run workflow**，選正式分支 `main`，再執行。
4. 等待 build 與 deploy 結果，核對新報告時間。

### GitHub CLI 方式

```powershell
gh auth status
gh workflow run daily-report.yml --repo cjw9223233/PMOT --ref main
gh run list --repo cjw9223233/PMOT --workflow daily-report.yml --limit 5
```

`gh auth status` 不通過時先完成 GitHub 登入。不要將 token 複製到程式、文件、Issue 或終端機截圖。

手動執行仍會查核交易日，沒有「強制休市產報告」選項。它會使用執行當下的行情與時間，不能拿下午補跑的結果冒充 08:00 的資訊集。[GitHub 手動工作流程文件](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

## 如何找到失敗的原因？

在 Actions 選定一次執行，展開失敗步驟。若使用 CLI，從 `gh run list` 複製該次 ID，將下列範例 ID 換成實際值：

```powershell
gh run view 123456789 --repo cjw9223233/PMOT --log-failed
```

每次事故記錄：台北日期時間、run URL、程式 commit、失敗階段、錯誤、哪些行情受影響、網站目前顯示哪份報告、處理方式與驗證結果。可開 GitHub Issue 保存；範本見[發展路線](ROADMAP.md)。

若資料已發佈，可依[資料指南](DATA_GUIDE.md)找到 `site/data/<識別字>.json`，檢查 `quotes` 與 `source_audit`。HTTP audit 只有成功／失敗與摘要，不保存完整原始回應；必要時重新查來源時，必須記錄新的查詢時間，不能宣稱重現了舊時點原文。

## 來源常見問題

| 現象 | 檢查與處置 |
| --- | --- |
| HTTP 429 | 來源限流。等待後重試一次，確認另一端點或既有備援能否使用；不要用高頻無限重試。 |
| TLS／憑證驗證失敗 | 核對電腦時間、系統信任憑證與公司代理設定；保留錯誤紀錄。不關閉 HTTPS 憑證驗證。 |
| 日期與日線不一致 | 查看錯誤內的來源常規行情日期及選出的日線日期。TSM 有日期別 Close 備援；其他指標目前沒有獨立供應商備援。 |
| TX 被判為日盤 | 確認查詢 `marketCode=1`、官方歸屬日、盤後時段文字與實際月份；不能拿日盤終值替代。 |
| 官方公告阻擋 | 程式對最近七日的相關標題採保守處理，目前不解析公告適用日期。人工閱讀公告並記錄是否誤阻，再以程式／測試修正或等待公告退出視窗；不直接刪掉門檻。 |
| 春節／跨年資料過舊 | 核對年度行事曆是否已發布，以及 4／5 個曆日的新鮮度門檻是否適用長假。以新案例修正規則，不把過期資料改標今天。 |

## Pages 與部署排查

1. **Settings → Pages → Source** 應為 **GitHub Actions**。
2. 確認 `deploy` job 的 `pages: write`、`id-token: write` 與 `github-pages` environment；確認保護規則允許本次 main 執行。
3. 檢查 build 是否已上傳名為 `github-pages` 的 artifact，以及 deploy 是否依賴 build。
4. 新資料已 commit、只有 deploy 失敗時，可在該次 run 使用 **Re-run failed jobs** 修復部署。重新執行整個每日流程會產生另一個實際時點的新報告。
5. GitHub 顯示部署成功而本機仍連不上時，分別記錄「部署結果」與「瀏覽器／網路連線結果」，兩者不能混為一談。

[GitHub Pages 自訂工作流程與部署權限](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)

## 如何回復上一份可靠報告？

這是維護者的人工恢復流程，使用分支與 PR 保留紀錄，**不要 force push、刪除歷史檔或手改報價**。

1. 記錄問題 run、commit 與報告識別字；若仍持續產出錯誤，可先在 Actions 暫停該工作流程，修復後再啟用。
2. 同步 main，建立維護分支；確認欲恢復報告的片段、獨立 HTML 與清單項目都存在。
3. 編輯 `site/data/reports.json`：將可靠項目放到第一筆；若問題項目不應再讓使用者選到，從清單移除它，保留其原檔供調查。
4. 執行 `python -m pmot build`。此命令讀第一筆重建首頁，不抓新行情，也不自行重新排序清單。
5. 跑測試、預覽首頁及日期選單，再以 PR 提交清單與首頁變更，記錄恢復原因。
6. 合併後該清單變更會觸發既有 build／deploy 流程；確認網站顯示可靠報告及其原始日期。處理根因後再確認下一次自動更新。

若故障是程式碼本身，使用修復／revert PR 恢復已驗證版本，再執行上述檢查；恢復來源程式並不會自動重建所有舊報告。

## 寫檔中斷的特殊情況

`publish()` 目前依序寫：內容片段 → 完整 HTML → JSON → 清單 → 首頁。尚未以暫存目錄整批驗證後切換。

中斷可能留下孤立檔案、缺檔的清單項目，或清單與首頁不同步。先核對清單每一筆的 `content`、`path`，再以可靠內容重建；不要直接重跑同一個識別字覆寫檔案。改用實際的新執行時間會建立新識別字。根因與殘留檔案處理請保留紀錄。


## 08:00 主排程與補跑

目前採每日 08:00、08:17、08:37（Asia/Taipei）三次觸發。當日報告已存在時，先比較部署成功收據，不會直接重抓行情。完整決策、時間欄位與重試步驟見 [每日交付機制](DELIVERY.md)。手動執行也採相同防重複規則；需要重新查詢行情時，須經人工檢查後調整清單，不能把部署重試當作更新報價。
