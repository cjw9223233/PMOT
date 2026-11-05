# 新手快速上手

[回 README](../README.md) · 下一篇：[架構與資料流程](ARCHITECTURE.md)

完成這份指南後，你應能在自己的電腦跑測試、閱讀既有報告，並知道第一次修改應從哪裡開始。預估 30 分鐘，安裝工具的時間另計。

## 1. 先認識三個詞（3 分鐘）

| 名詞 | 在本專案代表什麼 |
| --- | --- |
| 儲存庫（repo） | GitHub 上的完整專案；下載到電腦後可閱讀、修改與測試。 |
| CI/CD | GitHub 自動執行檢查、產生報告及部署網站的流程。 |
| 靜態網站 | 已產生的 HTML／CSS／JavaScript；訪客開頁面時不會重新抓行情。 |

本專案沒有資料庫伺服器、npm 安裝或 LLM 金鑰設定。每日正式更新由 GitHub Actions 執行。本機練習先使用儲存庫內的歷史資料。

## 2. 備妥工具（5 分鐘）

需要 Git、Python 3.12，以及瀏覽器。文字編輯器可使用你熟悉的工具。Node.js 只在你要修改並檢查 JavaScript 時需要。

開啟 **PowerShell**，逐行執行：

```powershell
git --version
py -3.12 --version
```

預期分別看到 Git 版本與 `Python 3.12.x`。如果沒有 `py`，但 `python --version` 顯示 Python 3.12，後續建立環境可改用 `python -m venv .venv`。找不到工具時，先完成 Git／Python 安裝並重新開啟終端機。

## 3. 下載與建立練習分支（5 分鐘）

以下把專案放在你的使用者目錄下。**如果已經有 PMOT checkout，進入既有資料夾即可，不要再次 clone 到同名資料夾。**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\source"
Set-Location "$env:USERPROFILE\source"
git clone https://github.com/cjw9223233/PMOT.git
Set-Location PMOT
git switch -c docs/my-first-change
git status
```

預期看到分支 `docs/my-first-change`，工作目錄沒有變更。公開 repo 的閱讀與下載不需要本專案的寫入權限；推送到原 repo 才需要權限。

## 4. 建立獨立 Python 環境（5 分鐘）

`.venv` 是這個專案自己的 Python 環境，已被 Git 忽略。以下直接指定環境中的 Python，因此不需要執行 PowerShell 的啟用腳本或調整執行原則。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Taipei')); print(ZoneInfo('America/New_York'))"
```

最後一行預期顯示 `Asia/Taipei` 與 `America/New_York`。若出現 `ZoneInfoNotFoundError`，表示本機缺 IANA 時區資料，請安裝後重試：

```powershell
.\.venv\Scripts\python.exe -m pip install tzdata
```

Python 的 `zoneinfo` 優先讀取系統時區資料，找不到時可使用 `tzdata`；Windows 通常需要這個補充套件。GitHub 的 Ubuntu runner 已有系統時區資料。[Python 時區資料說明](https://docs.python.org/3.12/library/zoneinfo.html#data-sources)

macOS／Linux 可用 `python3.12 -m venv .venv` 建立環境，之後將範例中的 `.\.venv\Scripts\python.exe` 改為 `.venv/bin/python`。

## 5. 跑測試與網站（7 分鐘）

**在包含 README 與 `pmot` 資料夾的專案根目錄執行：**

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pmot build
.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory site
```

第一個指令預期顯示測試名稱並以 `OK` 結束；截至 2026-11-05 的基準是 25 項，後續新增測試後數量可能增加。這些測試使用合成資料與測試替身，不需要連線到行情來源。

第二個指令從現有報告清單重建首頁，成功時通常沒有額外輸出。第三個指令會持續執行；請保持該終端機開啟，用瀏覽器進入 [本機網站](http://127.0.0.1:8000/)。按 `Ctrl+C` 可停止伺服器。

確認以下結果：

- 看得到六項市場章節與綜合判讀。
- 日期選單能切換現有歷史報告；切換後網址會帶 `?report=...`。
- 頁面顯示的報告日期可能不是今天，因為這次讀的是既有歷史資料。
- 手機寬度下能閱讀，列印按鈕能開啟瀏覽器的列印視窗。

直接雙擊 `site/index.html` 也能讀內容，但瀏覽器可能限制 `file://` 下的歷史資料載入；請使用上述 HTTP 伺服器練習完整功能。

## 6. 第一個小修改（5 分鐘）

開啟 `site/assets/report.css`，在檔案末尾加入一個練習樣式：

```css
/* 練習：調整左上角品牌文字的字距。 */
.brand { letter-spacing: .08em; }
```

重新整理本機網站，確認左上角品牌文字出現變化，再執行：

```powershell
git diff -- site/assets/report.css
git status --short
```

預期差異只包含你的樣式修改。這個練習完成後，可依[開發與發版指南](DEVELOPMENT.md)提交 PR；若只是練習，在編輯器移除剛加入的規則即可。

## 7. 什麼時候才執行 update？

`python -m pmot update` 會連網、檢查台北當天的交易狀態，並在成功時建立新的報告與更新首頁。它不是「重新整理畫面」的指令。進行實際行情查核前，先讀[維運手冊](OPERATIONS.md)。

如果要獨立練習實際更新，可指定測試目錄，避免把測試產出混入正式網站：

```powershell
.\.venv\Scripts\python.exe -m pmot update --site tmp/live-check
```

`tmp` 不會提交到 Git。正常交易日且至少一組主要市場資料通過驗證時，會在該目錄產生報告；休市會略過，交易日或全部主要來源無法確認會失敗。新目錄在略過或失敗時可能沒有首頁，屬預期結果。

## 常見卡關

| 現象 | 下一步 |
| --- | --- |
| `No module named pmot` | 確認終端機位於 repo 根目錄，而不是 `pmot` 或 `site` 裡。 |
| 找不到 Python／Git | 確認安裝完成、版本正確，重開終端機。 |
| `ZoneInfoNotFoundError` | 在同一個 `.venv` 安裝 `tzdata`，不要改成固定美國 UTC offset。 |
| 8000 埠已被使用 | 將伺服器指令的 8000 改成 8001，網址也改為 8001。 |
| 網站日期不是今天 | 先確認是歷史預覽、休市、更新失敗，還是排程延遲；不要手改日期。 |
| SSL／429／連線逾時 | `build` 與測試仍可先完成；實際更新的排查見維運手冊，不關閉 TLS 驗證。 |

環境原理可參考 [Python venv 官方文件](https://docs.python.org/3.12/library/venv.html)。
