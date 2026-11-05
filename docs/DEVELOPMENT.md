# 開發與發版指南

[回 README](../README.md) · 前一篇：[維運](OPERATIONS.md) · 下一篇：[發展路線](ROADMAP.md)

先完成[快速上手](GETTING_STARTED.md)，確認既有測試與本機網站可運作，再修改功能。

## 修改入口對照

| 需求 | 主要修改位置 | 一起檢查 |
| --- | --- | --- |
| 顏色、字級、手機版面 | `site/assets/report.css` | 桌面、手機、長數字及列印。 |
| 報告文字、卡片、綜合結論 | `pmot/render.py` | 既有 HTML 不會自動重算；預覽新產出的報告及缺值狀態。 |
| 來源網址、解析格式與日期檢查 | `pmot/sources.py` | 合成回應測試、單位、時區、失敗與過期案例。 |
| 查詢組合、發布門檻 | `pmot/__main__.py` | 交易日、部分／全部失敗、`changed` 輸出。 |
| HTTPS／重試／查核紀錄 | `pmot/http.py` | 有限重試、資料大小、錯誤保留、無真實網路的測試替身。 |
| 歷史選單、分享網址 | `site/assets/app.js` | 切換成功／失敗、連續快速切換、既有內容保留。 |
| 觸發時間、權限、部署 | `.github/workflows/` | 事件分支、路徑過濾、job 權限及真實執行紀錄。 |

## 正常開發循環

以下 `python` 應使用已確認的 Python 3.12；Windows 虛擬環境可用 `.\.venv\Scripts\python.exe` 取代。

```powershell
git status --short
git switch main
git pull --ff-only
git switch -c docs/describe-your-change
```

開始前若已有未提交變更，先確認它們的用途與歸屬，不要覆寫或直接切走。本例分支名稱請改成自己的需求，例如 `fix/tx-session-date`。

完成修改後：

```powershell
python -m unittest discover -s tests -v
node --check site/assets/app.js
git diff --check
git diff --stat
```

Node.js 檢查只在修改 JavaScript 時需要。純文件變更仍應驗證相對連結與命令；註解／docstring 變更要確認沒有改到程式邏輯。不要把真實報價寫進測試來補欄位。

### 預覽既有資料

```powershell
python -m pmot build
python -m http.server 8000 --bind 127.0.0.1 --directory site
```

`build` 重包最近內容片段與頁面外框，因此可以驗證 page 外框及共用資產，但**不會重新執行 `render_report()` 產生內文**。修改 renderer 內文後，應用合成資料在 `tmp` 測試目錄呼叫 `publish()` 或透過測試檢查結果；需要真實來源時才做明確的 `update --site tmp/live-check`。

正式網站內不放合成報告。新增的例子或 fixture 必須明確標示「合成測試資料」，並讓測試在暫存目錄完成。

## 如何新增或替換來源？

1. 先記錄來源、商品識別、單位、日期／時區、收盤定義、更新頻率與可能延遲。
2. 將下載函式與 `parse_*()` 分開；解析器接收字串／JSON 及可注入的 `now`，讓測試不依賴實際網路與今天日期。
3. 依[資料契約](DATA_GUIDE.md)回傳成功物件，失敗時拋出明確例外；不要回傳零或猜測日期。
4. 加入正常、缺值、未完成、過期、商品不符與口徑衝突的測試，再接到入口的任務表。
5. 若新增第十組資料或第七章，需同步任務表、fallback URL、renderer、清單狀態、前端導覽、測試與文件，避免硬編碼的九組／六章說法過期。
6. 備援來源必須單獨核對口徑。Yahoo 的兩個主機仍是同一供應商，不能算兩個獨立來源的交叉確認。

## 教學型註解約定

- 模組 docstring 交代責任、閱讀入口與邊界；重要函式交代輸入、輸出、單位及拒收條件。
- 區塊註解解釋原因，例如「為何不用 `chartPreviousClose`」或「週五夜盤為何不能用週一當結束日」。
- 避免逐行重述 Python 語法；字元清理、`lambda`、非同步請求版本等對新手陌生的地方可補一個小例子。
- 註解應描述目前程式。尚未實作的改善放進 roadmap，不能用註解宣稱已有交易所行事曆引擎、完整 HTML 消毒或原子寫檔。
- 不將 HTML 顯示文字改成教學文字；程式學習內容放文件與原始碼註解。

## 提交與 PR

確認差異只含本次需求的來源、測試與文件，再選擇明確檔案提交。以下示範文件修改：

```powershell
git add README.md docs
git diff --cached --check
git diff --cached --stat
git commit -m "Document beginner onboarding and maintenance"
git push -u origin docs/describe-your-change
gh pr create --base main --title "補齊新手與維護文件" --body-file tmp/pr-description.md
```

最後一行前需先建立 PR 說明檔；`tmp` 已被忽略，說明檔不會被提交。沒有原 repo 寫入權限時，透過自己的 fork 推送，再向原 repo 開 PR。

PR 說明包含：修改目的、實際變更、驗證方式／結果、已知限制與是否影響資料格式或排程。不要貼 token 或把失敗檢查寫成通過。

## 發版與維護者檢查

1. 確認 PR 的 `Validate source changes` 通過；檢查是否修改了自動產物、報價或工作流程權限。
2. 若 main 已有新的自動報告提交，先同步並檢查衝突，保留真實歷史資料；不要用 force push 覆蓋 main。
3. 合併到 main 後，符合 paths 的程式／資產變更會觸發重建與部署。純文件變更不一定需要部署，不能以沒有部署 run 判定合併失敗。
4. 部署完成後檢查首頁日期、缺漏提示、歷史選單、桌面／手機；需要驗證新行情邏輯時，再手動執行每日流程。
5. 將事故、決策與待辦連回 Issue／PR。本專案目前以 commit、PR 與 Actions run 追蹤版本，尚無自動語意化版本／Release 流程。

自動報告的提交會帶 `[skip ci]`；人工功能與文件 PR 不應仿照加入這個標記，否則可能跳過原本應執行的檢查。[GitHub 跳過工作流程說明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)

## 文件同步清單

- 資料欄位或判讀規則：同步 `DATA_GUIDE.md`、測試及根目錄 prompt。
- 實際操作／錯誤行為：同步 `OPERATIONS.md`。
- 新依賴或建置方式：同步 `GETTING_STARTED.md`、README 與必要的工作流程。
- 規格 prompt 變更：確認根目錄版本與 `site/prompt.md` 副本一致；修改文字不會自動修改 Python 邏輯。
- 既有限制修復：在 `ROADMAP.md` 記錄驗收證據與 PR，不把待辦直接刪到無法追蹤。
