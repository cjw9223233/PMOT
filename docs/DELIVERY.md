# 每日交付機制與驗收

[回 README](../README.md) · [先看自動化流程圖與分工](AUTOMATION.md)

外部喚醒實作與設定見 [Cloudflare 免費方案](CLOUDFLARE_SETUP.md)。Actions 另保存 `.pmot/check.json` 讓 Worker 辨識當日官方查核的開市／休市／未知；此檔不含行情，也不會因休市而部署網站。`trigger_source` 與 `external_requested_at` 僅供追蹤，不繞過原判斷。

每天台北時間 08:00 主排程，08:17、08:37 補跑，均由同一 GitHub Actions 流程執行。每次均重新查核官方交易日；休市略過，查核不明則失敗並保留原網站。GitHub 排程仍可能共同延遲，不保證 09:00 前完成；需要硬性時效時須另設獨立觸發及監測。

## 新手閱讀順序

先讀 `pmot/delivery.py` 的 `prepare()`，再看工作流程中的 prepare → query → package → deploy → confirm。原本的 `python -m pmot update` 仍是明確要求抓新行情的低階命令；Actions 與手動 workflow_dispatch 先經交付狀態機防重複。

| 狀態 | 動作 |
| --- | --- |
| 休市 | 不產報告、不部署 |
| 官方交易日查核失敗 | 停止，不猜測正常交易日 |
| 今日沒有報告 | 查新行情，寫不可覆寫快照，再部署 |
| 今日有報告，沒有相符成功收據 | 重用同一快照重新部署，不增加報告、不改報價 |
| 今日有報告且收據相符 | 略過 |
| main 程式或版面更新的 push | 重建既有首頁並部署，不查新行情 |

收據比對報告日期、內容路徑、三份快照雜湊，以及首頁／資產／prompt 雜湊。缺檔或內容損壞時會報錯，不能當作成功。整個工作流程使用同一 concurrency group，checkout main 在前次流程結束後才開始，以讀到最新收據。保留 GitHub concurrency 本身可能替換等待中執行的限制。

## 部署失敗怎麼恢復

Pages action 一次最多等待兩分鐘，第一次失敗後於同一 run 再試一次；兩次皆失敗則整個 run 失敗，不寫成功收據。08:17、08:37 或手動執行會重用當日快照重試部署。

只有 Pages 回報成功後，才將 `.pmot/deployment.json` 提交至 main。收據綁定 run ID、attempt 與報告／網站內容；若期間內容改變，拒絕寫入。收據提交失敗也會讓 run 失敗；下一次可安全重複部署。收據提交帶 `[skip ci]`，不會形成循環。

若要重試，於 Actions 選擇 `Daily market report and GitHub Pages` → Run workflow（main）。建議開新 run，讓它先讀最新狀態；不要直接重跑歷史 run 的 deploy job。歷史 attempt 的網站套件不一定符合 main 最新內容，確認步驟會拒絕錯配。

## 時間證據

| 欄位 | 意義 |
| --- | --- |
| `target_at` | 當日 08:00 目標時間，並非實際完成時間 |
| `trigger_expected_at`、`trigger_delay_seconds` | schedule 事件相對自身 08:00／08:17／08:37 時槽的建立延遲 |
| `run_created_at` | GitHub API 回報 run 建立時間 |
| `workflow_started_at` | GitHub API 回報 run 啟動時間 |
| `prepared_at` | Python 交付決策開始時間 |
| `generated_at` | 原快照實際產出時間；重試沿用原值 |
| `deployment_requested_at` | 打包部署準備時間，並非 Pages API 精確受理時間 |
| `deployment_completed_at` | Pages action 成功後寫收據的確認時間，略晚於 Pages 回報成功時間 |
| `timeliness` | 新收據另列 09:00 截止與 `on_time`／`late`／`unconfirmed`；成功部署不等於準時 |

Actions Summary 與保留 30 天的 timing artifact 提供該次決策及已知時間（交易日查核失敗、尚未寫 timing 時可能沒有 artifact）。網站 `site/data/delivery.json` 是打包當下的 pending 紀錄，不能預填部署成功。瀏覽器另外讀取 main 上公開成功收據，核對 run、attempt、內容後顯示確認時間；連線失敗或快取未更新時標示「未確認」，可點 Actions 紀錄查證。頁面仍可正常閱讀，不依賴成功收據連線才能顯示行情。

本機不產生假的成功部署收據。`delivery confirm` 只由工作流程在 Pages action 成功後呼叫；收據是本專案的狀態紀錄，並不是遠端網站的獨立可用性探測。Pages 成功也不能代表所有地區 CDN 已同步。

時效以台北報告日 **09:00 前**的實際部署確認為準，09:00:00 已算逾時。成功部署後、或補跑因已交付而略過時，Actions Summary 都會另外列時效，逾時／未確認會產生 warning，部署狀態仍保留真實成功結果。網站也依相符收據的完成時間標示「09:00 前完成」或「逾 09:00」；舊收據不需補造時間。尚未喚醒的 workflow 無法自行在 09:00 發出警示，這不是獨立即時監測。

[2026-11-17 稽核](audits/2026-11-17-schedules.md)確認三個時槽仍會共同延遲數小時。使用者選擇先保留 GitHub 排程；本次僅修正狀態揭露，不宣稱已解決排程準時問題，也未建立外部觸發或常駐 AI 監控。

## 驗收

執行 `python -m unittest discover -s tests -v`，涵蓋無當日報告、舊日期、缺快照、重試不改快照、成功略過、失敗／錯配收據、資產變動、休市／未知交易日、pending 不冒充成功、錯誤 run／內容拒絕確認。

發版時先通過本機與 PR CI，再合併 main 驗證 Pages 成功及收據提交；手動再執行一次，確認當日已交付就 skip。接下來三個正常交易日應核對三時槽的實際觸發時間、正常部署後補跑略過，以及公開網站的當日報告日期。這是後續觀察項目，發版當日不能宣稱已完成三日驗收。

排程延遲依據：[GitHub 官方 schedule 說明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
