# 2026-11-17 排程與交付時效稽核

[回交付指南](../DELIVERY.md)

範圍：11/13 行事曆修正後至 11/17 上午。時間皆為 Asia/Taipei。資料由 GitHub run API、各次 `delivery-timing-1` artifact、job API、報告 JSON 與成功收據交叉核對。確認了 11/13–11/16 共 12 次 schedule 執行；11/17 於 08:56 查核時尚無當日 schedule run，不預判稍後的結果。

## 結論

行事曆修正後沒有再出現錯年失敗；正常日來源查詢、部署、成功後補跑略過、週末不新增報告均正常。但是三個時槽皆延遲數小時，尚未達成全自動開盤前交付。11/13 與 11/17 的開盤前交付均來自本對話手動補跑，不能算自動排程準時。

| 日期 | 08:00 實際啟動 | 08:17 實際啟動 | 08:37 實際啟動 | 首份報告部署確認 | 09:00 前完成？ |
| --- | --- | --- | --- | --- | --- |
| 11/13（五） | 11:43:58 | 14:44:54 | 15:14:29 | 08:25:17，手動 | 是，但非自動排程；三次皆略過 |
| 11/14（六） | 11:42:10 | 14:22:07 | 14:59:25 | 無新報告 | 休市，三次皆略過 |
| 11/15（日） | 11:19:14 | 14:30:35 | 15:09:25 | 無新報告 | 休市，三次皆略過 |
| 11/16（一） | 11:20:31 | 14:27:55 | 15:14:09 | 11:21:06，主排程 | 否；兩次補跑已交付而略過 |
| 11/17（二） | 08:56 查核時尚未啟動 | 同左 | 同左 | 08:57:29，手動 | 是，但非自動排程；自動結果尚待發生 |

11/13 手動紀錄：[43336778607](https://github.com/cjw9223233/PMOT/actions/runs/43336778607)。11/16 主排程：[43797599511](https://github.com/cjw9223233/PMOT/actions/runs/43797599511)。11/17 手動紀錄：[43991717946](https://github.com/cjw9223233/PMOT/actions/runs/43991717946)。11/13、11/16、11/17 的報告均確認 9／9 組資料。

## 每次 schedule 證據

| 日期 | 原訂時槽 | run 建立／啟動 | 觸發延遲 | 決策 | build／deploy |
| --- | --- | --- | --- | --- | --- |
| 11/13 | 08:00 | [11:43:58](https://github.com/cjw9223233/PMOT/actions/runs/43360893420) | 03:43:58 | 已交付略過 | success／skipped |
| 11/13 | 08:17 | [14:44:54](https://github.com/cjw9223233/PMOT/actions/runs/43380848062) | 06:27:54 | 已交付略過 | success／skipped |
| 11/13 | 08:37 | [15:14:29](https://github.com/cjw9223233/PMOT/actions/runs/43384315031) | 06:37:29 | 已交付略過 | success／skipped |
| 11/14 | 08:00 | [11:42:10](https://github.com/cjw9223233/PMOT/actions/runs/43552977164) | 03:42:10 | 週末略過 | success／skipped |
| 11/14 | 08:17 | [14:22:07](https://github.com/cjw9223233/PMOT/actions/runs/43565992522) | 06:05:07 | 週末略過 | success／skipped |
| 11/14 | 08:37 | [14:59:25](https://github.com/cjw9223233/PMOT/actions/runs/43568939552) | 06:22:25 | 週末略過 | success／skipped |
| 11/15 | 08:00 | [11:19:14](https://github.com/cjw9223233/PMOT/actions/runs/43671820972) | 03:19:14 | 週末略過 | success／skipped |
| 11/15 | 08:17 | [14:30:35](https://github.com/cjw9223233/PMOT/actions/runs/43685756655) | 06:13:35 | 週末略過 | success／skipped |
| 11/15 | 08:37 | [15:09:25](https://github.com/cjw9223233/PMOT/actions/runs/43688663488) | 06:32:25 | 週末略過 | success／skipped |
| 11/16 | 08:00 | [11:20:31](https://github.com/cjw9223233/PMOT/actions/runs/43797599511) | 03:20:31 | 新建報告 | success／success |
| 11/16 | 08:17 | [14:27:55](https://github.com/cjw9223233/PMOT/actions/runs/43816918105) | 06:10:55 | 已交付略過 | success／skipped |
| 11/16 | 08:37 | [15:14:09](https://github.com/cjw9223233/PMOT/actions/runs/43822351585) | 06:37:09 | 已交付略過 | success／skipped |

## 原因與修正範圍

11/16 run 建立於 11:20:31，build 約 20 秒，整次流程至 11:21:10 約 39 秒；收據確認 11:21:06。延遲發生在 run 建立前，非 Python 抓行情或 Pages 部署耗時。主排程延遲約 3 小時 19 分至 3 小時 44 分；補跑延遲超過 6 小時，同一排程器的備援沒有避開共同延遲。GitHub 公開 API 無法揭露平台內部具體原因，不能斷言是某次特定事故。

[GitHub 官方文件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)說明高負載可造成 schedule 延遲；避開整點可降低機率，但不是準時保證。目前兩次非整點補跑也已證實延遲。

使用者於本次稽核選擇「先保留 GitHub，完成稽核與狀態修正」。維持 08:00、08:17、08:37，不加入獨立雲端觸發。新增 Actions Summary／成功收據的時效欄位、逾時 warning 及網站本次部署時效標示；部署成功與準時分開呈現，精確 09:00:00 算逾時。測試的合成狀態訊息不再輸出成 Actions annotation。

此修改改善揭露，沒有修復 GitHub 排程器，也不能在 workflow 尚未啟動時即時告警。未來若需可靠地避開此共同延遲，須另行決定獨立觸發或其他執行平台；不能僅增加更多 GitHub cron 就聲稱問題已解決。沒有建立額外本機自動化或 AI 背景監控。

本表使用每天首次成功交付的歷史證據；後續版面改版重新部署的收據時間可能更晚，不能拿它倒推當日原報告未曾準時交付。網站的「本次部署時效」則針對該份目前部署版本。
