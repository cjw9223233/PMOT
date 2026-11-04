# PMOT｜台股開盤前外部市場觀察

沿用已確認的 HTML 版型，將美股三大指數、台積電 ADR、費城半導體、台指期夜盤、美國 10 年期公債殖利率與美元指數整理為單頁網站。

- 網站：[cjw9223233.github.io/PMOT](https://cjw9223233.github.io/PMOT/)
- 排程：每天 **08:30 Asia/Taipei** 觸發，先查核 TWSE 官方年度休市行事曆與新聞公告。正常交易日產出新報告，休市日保留最近報告。
- 首頁為最新報告；日期選單可切換歷次報告，支援手機、章節導覽、分享選定日期與列印。
- 每項區分【事實】【解讀】【不確定性】，附來源、實際日期時間、單位及計算口徑。無法確認的資料不補值。
- 不需要 API 金鑰、LLM 或本地電腦持續開機。解讀為固定規則，不自動捏造市場事件。

## 自動更新流程

`GitHub Actions → 交易日與公告查核 → 獨立來源查詢 → 日期／時段／單位驗證 → HTML + JSON → Git commit → GitHub Pages`

程式使用 Python 3.12 標準函式庫。行情來源可能限流；每一項各自失敗時列「資料未確認」。全部市場來源失敗、交易日無法確認或近期有需人工判讀的休市公告時，工作流程失敗並保留上一份報告。官方新聞清單的異動檢查採保守門檻，可能需要人工確認；不得把未確認狀態當作正常開市。

GitHub 排程可能延遲，**08:30 是觸發時間，不是保證完成時間**。報告以實際完成與資料截止時間為準；逾 09:00 時自動標示。公開儲存庫的排程可能因長期無活動而停用，需於 Actions 檢查狀態。[GitHub 排程說明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 本機使用

```powershell
python -m unittest discover -s tests -v
python -m pmot build       # 僅以既有報告重建首頁，不查詢新行情
python -m pmot update      # 依台北當日日期查詢、確認交易日才建立新報告
python -m http.server 8000 --directory site
```

開啟 `http://localhost:8000`。歷史切換需要 HTTP 伺服器；直接開 HTML 仍可閱讀預先產出的最新內容。

## GitHub Pages 設定

儲存庫 **Settings → Pages → Source → GitHub Actions**。需啟用 Actions，允許此工作流程使用 `contents: write`、`pages: write`、`id-token: write`。資料更新流程先通過測試，才儲存報告並發佈。可在 Actions 手動執行 `Daily market report and GitHub Pages` 驗證最新一次資料抓取。

## 專案結構

- `pmot/`：查詢、資料驗證、規則判讀與 HTML 產生器。
- `site/`：可直接部署到 Pages 的靜態網站。
- `site/data/`：各次報告內容、結構化報價、來源查核紀錄與報告清單。
- `site/reports/`：每次報告的獨立 HTML；不覆寫歷史報告。
- `tests/`：交易日、時段、日期、期貨合約、殖利率單位與缺漏保護測試。
- `台股開盤前外部市場觀察清單_prompt.md`：完整報告規格；網站內亦提供其副本。

初始歷史報告為 2026-11-04 09:08:56 的手動試跑，保留原始資料時點與限制；不是新的自動更新結果。

本報告是市場觀察工具，不是保證行情方向的預測，也不是個別股票的買賣建議。
