# 資料規格與判讀規則

[回 README](../README.md) · 前一篇：[架構](ARCHITECTURE.md) · 下一篇：[維運](OPERATIONS.md)

本文件描述目前程式行為。讀取結構化資料時，先看 `ok`、日期、時間與口徑，再看數值。

## 六項章節、九組資料

| 報告章節 | `quotes` 鍵 | 單位／用途 |
| --- | --- | --- |
| 1. 美股三大指數 | `sp500`、`nasdaq`、`dow` | 點；同一來源相鄰完成交易日的收盤比較。 |
| 2. 台積電 ADR | `tsm` | USD；Yahoo 失敗時可使用 Stock Analysis 的未調整 Close。 |
| 3. 費城半導體 | `sox` | 點；不是半導體 ETF 價格。 |
| 4. 台指期夜盤 | `tx` | 點；期交所實際月份合約的盤後最後成交價。 |
| 4. 夜盤的現貨比較 | `spot` | 前一台股交易日加權指數收盤，僅供期現位置差。 |
| 5. 美國 10 年期殖利率 | `treasury` | %；Treasury 每日 10 Yr 平價殖利率曲線值。 |
| 6. 美元指數 | `dxy` | 點；有時間戳的最新快照，不標成正式收盤。 |

因此輸出 `confirmed 9/9` 是九組資料通過各自的程式驗證，不是九個市場，也不保證九組資料同時點、即時或經獨立來源全面交叉驗證。

## 自動報告 JSON 外層

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `schema_version` | 整數 | 目前為 1；未來若改欄位契約應規劃相容性。 |
| `date` | 字串 | 本次執行開始時的台北報告日期，`YYYY-MM-DD`。 |
| `scheduled_time` | 字串 | `08:00 Asia/Taipei`；不是實際完成時間。 |
| `cutoff` | ISO 8601 字串 | 查詢工作完成後的台北時間，含 `+08:00`。 |
| `generated_at` | ISO 8601 字串 | 呼叫發佈前記錄的產出時間；不是遠端網站部署完成時間。 |
| `gate` | 物件 | 正常交易日理由、年度行事曆 URL、公告 URL、掃描到的相關公告。 |
| `quotes` | 物件 | 上表九組資料，各有獨立狀態。 |
| `source_audit` | 陣列 | HTTPS 取得內容的紀錄；與報價解析成功是不同階段。 |

本機可從最新清單找自動報告 JSON。種子手動報告可能只有 HTML，沒有相同檔名的 JSON，不能當成寫檔失敗。

```powershell
$items = Get-Content -Raw -Encoding UTF8 site/data/reports.json | ConvertFrom-Json
$latest = $items[0]
$latest
$jsonPath = 'site/' + ($latest.content -replace '\.html$', '.json')
if (Test-Path -LiteralPath $jsonPath) {
    Get-Content -Raw -Encoding UTF8 -LiteralPath $jsonPath | ConvertFrom-Json
}
```

## 單組行情契約

成功資料通常包含：`ok=true`、`symbol`、`value`、`date`、`time`、`unit`、`status`、`calculation`、`sources`。一般漲跌資料另含 `previous`、`previous_date`、`change`、`percent`。

**以下是合成教學數據的局部片段，不是真實報價，也不是可直接輸入 renderer 的完整報告：**

```json
{
  "ok": true,
  "symbol": "TSM",
  "value": 104,
  "previous": 100,
  "previous_date": "2026-11-02",
  "date": "2026-11-03",
  "change": 4,
  "percent": 4,
  "unit": "USD",
  "time": "教學用時間說明",
  "status": "合成測試資料",
  "calculation": "(104 / 100 - 1) × 100 = 4%",
  "sources": ["https://example.com/"]
}
```

失敗資料為 `ok=false`、`value=null`、`error`，組裝階段補上查詢 `sources`。renderer 先判斷 `ok`，不把 null 或缺值當成零漲跌。

例外契約：

- `spot` 只有比較用的 `ok`、`date`、`value`、`sources`，不直接送進一般行情卡片。
- `tx` 沒有獨立核實的 `previous`；有 `contract`、`open`、`high`、`low`、`session_start`、`session_end`。漲跌與百分比保留官方欄位。
- `treasury` 另有 `basis_points`；`change` 是**百分點差**，不是相對漲跌幅。

## 來源查核與報告狀態

HTTPS 成功紀錄包含 `url`、`retrieved_at`、`status="ok"`、`sha256`；失敗紀錄包含 `url`、`status="failed"`、`error` 類型。目前失敗紀錄沒有獨立時間戳，也沒有保存來源原文。

`sha256` 是收到的原始位元組摘要，用來辨識內容；只有摘要無法還原來源，也不代表報價正確。下載成功後，解析器仍可能因日期或格式不符而拒收，所以 audit 的 `ok` 不等於行情物件的 `ok=true`。

歷史清單的 `status`：

| 值 | 目前定義 |
| --- | --- |
| `verified` | 九組行情物件的 `ok` 全為 true，通過現行解析器門檻。 |
| `partial` | 至少一組 `ok` 不為 true；其餘確認資料仍可呈現。 |

## 日期與時間規則

- 全站報告日期使用 `Asia/Taipei`；美股交易日期使用 `America/New_York`，由時區資料處理夏令／冬令時間。
- 美股日線以美東 16:00 加 10 分鐘作為保守完成門檻，至少要有兩筆完成日線；來源常規行情日期必須與選出的最後一筆日線一致，且不得在未來。這不是完整的 NYSE 休市／提早收盤行事曆引擎。
- Yahoo 與 ADR 備援對最新資料採 4 個曆日的新鮮度上限；Treasury 與現貨採 5 個曆日上限。門檻無法證明資料一定是最新應有交易日，長假可能需要調整規則及測試。
- DXY 最新快照不能在未來，距查詢時間不得超過 30 小時；比較基準從同來源日線挑報價日期之前的最近一筆。
- TX 官方歸屬交易日須為台北當日，且頁面明列盤後時段。實際夜盤結束日期從起始日期加一天推算，不能直接用歸屬日覆寫；週五夜盤可能歸屬週一，但實際在週六 05:00 結束。
- `time` 是來源時間的說明字串，不保證每項都是可解析的 ISO 時間；不得將查詢時間當成最後成交時間。

## 計算與單位

| 項目 | 規則 |
| --- | --- |
| 收盤漲跌 | `value - previous`。 |
| 收盤漲跌幅 | `(value / previous - 1) × 100`；顯示時四捨五入。 |
| 殖利率基點 | `(本日百分比值 - 前日百分比值) × 100`；例如 4.95% − 4.91% = 0.04 百分點 = 4 基點。此為計算示例。 |
| 期現位置差 | 夜盤期貨終值 − 前日現貨收盤；時間與商品不同，不是保證開盤缺口。 |

`number()` 只清理字元並轉成數字，不推定金融單位，也不做縮放。例如 `▲4%` 轉成數字 4，百分比的意義由呼叫端決定。程式不對未取得的 `^TNX` 猜測乘除 10。

## 固定判讀規則

- 單一股票／指數／期貨：資料成功且 `change > 0` 為偏多，`< 0` 為偏空，`= 0` 為分歧；資料失敗為「分歧（資料不足）」。
- 美股整體：三項都成功且同為正或負才判偏多／偏空；其他情況為分歧。
- 利率與美元：兩項都成功且同降為有利風險偏好，同升為不利；其餘為訊號不明。
- 綜合結論：美股整體、費半、ADR、夜盤四項全部偏多／偏空時才形成一致方向；否則為訊號分歧或資料不足。
- 夜盤 OHLC 不能得知高低點先後；程式只說明終值相對開盤及波動，不宣稱已判定盤中反轉。

這些是可追溯的觀察規則，不是學習模型或新聞因果分析。需求改變時，必須一起修改程式、測試與文件；單改 prompt 不會改變執行結果。
