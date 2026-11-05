"""把驗證結果轉成固定快照、歷史清單及首頁。

閱讀路線：格式化 helpers → render_report() 內文與固定判讀 → page() 外框
→ publish() 新增歷史檔 → build_index() 用清單第一筆重建首頁。
本模組不下載行情；現行寫檔不是整批原子操作，限制見維運手冊。
"""
from html import escape
from pathlib import Path
import json

NAMES = [
    ('美股三大指數', '^GSPC／^IXIC／^DJI'), ('台積電 ADR', 'TSM · USD'),
    ('費城半導體指數', '^SOX'), ('台指期夜盤最終走勢', 'TX · 盤後交易'),
    ('美國 10 年期公債殖利率', 'Treasury · 10 Yr'), ('美元指數', 'DXY／DX-Y.NYB')]


def e(v):
    """把資料轉成可安全放入 HTML 文字／引號屬性的字串，不用於整段既有 HTML。"""
    return escape(str(v), quote=True)


def fmt(value, digits=2, signed=False):
    """只處理顯示精度與正負號；None 顯示未確認，不將它轉成零。"""
    if value is None:
        return '資料未確認'
    return format(value, f'{"+" if signed else ""},.{digits}f').replace('-', '−')


def tone(value):
    """台灣慣例紅漲綠跌由 CSS 決定；保留正負號讓方向不只靠顏色辨識。"""
    return 'up' if value > 0 else 'down' if value < 0 else 'neutral'


def note(kind, value):
    """建立事實／解讀／不確定性區塊，內容一律先跳脫。"""
    cls = {'事實': 'fact', '解讀': 'reading', '不確定性': 'uncertain'}[kind]
    return f'<div class="note {cls}"><b>【{kind}】</b><p>{e(value)}</p></div>'


def links(urls):
    """依原順序去除重複 URL，只顯示 HTTPS 查詢連結。"""
    unique = list(dict.fromkeys(urls))
    return '<div class="sources"><span>查詢來源</span>' + ''.join(f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">來源 {n} ↗</a>' for n, url in enumerate(unique, 1) if url.startswith('https://')) + '</div>'


def key_values(items):
    """將 (欄位名, 顯示值) 序列轉成資訊區塊；值可含未提供時間的說明文字。"""
    return '<dl class="key-values">' + ''.join(f'<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for k, v in items) + '</dl>'


def section(n, body, label=''):
    """依六項固定順序建立章節，ID 同時提供前端導覽的錨點。"""
    name, subtitle = NAMES[n - 1]
    return f'<section id="market-{n}" class="market"><header class="section-head"><span class="number">{n:02}</span><div><h2>{name}</h2><p>{subtitle}</p></div><span class="badge neutral">{e(label)}</span></header>{body}</section>'


def quote_block(item):
    """先判斷 ok，再依單位產生行情卡片；失敗時只呈現缺漏與來源。

    殖利率顯示基點／百分點，一般行情顯示漲跌與百分比，避免把兩種量混用。
    """
    if not item.get('ok'):
        return note('不確定性', '資料未確認：' + item.get('error', '來源未提供可驗證數據')) + links(item.get('sources', []))
    if item.get('unit') == '%':
        move = f'{fmt(item["basis_points"], signed=True)} 基點'
        percent = f'{fmt(item["change"], signed=True)} 百分點'
    else:
        move = f'{fmt(item["change"], signed=True)} {item["unit"]}'
        percent = f'{fmt(item["percent"], signed=True)}%'
    body = f'<div class="quote-row"><div><span class="mini-label">【事實】{e(item["date"])} · {e(item["symbol"])}</span><div class="quote">{fmt(item["value"], 3 if item["symbol"] == "DX-Y.NYB" else 2)} <small>{e(item["unit"])}</small></div></div><div class="change {tone(item["change"])}">{e(move)} <span>{e(percent)}</span></div></div>'
    baseline = f'{item.get("previous_date", "未提供日期")} · {fmt(item.get("previous"))} {item["unit"]}' if 'previous' in item else '漲跌採官方欄位；比較基準定義未另核實'
    body += key_values([('報價日期／時間', item['time']), ('比較基準', baseline), ('資料狀態', item['status']), ('計算口徑', item['calculation'])])
    return body


def direction(item):
    """將成功行情的 change 正負映射為觀察訊號；缺資料永遠不推定偏多／偏空。"""
    if not item.get('ok'):
        return '分歧（資料不足）'
    change = item['change']
    return '偏多' if change > 0 else '偏空' if change < 0 else '分歧'


def render_report(data):
    """接收完整九組 quotes 與 gate／日期時間，回傳報告內容 HTML。

    只根據已確認資料套用固定規則，不分析新聞、不保證市場因果或開盤方向。
    需保留六章順序、A／B／C 摘要與缺漏提示；新增資料時同步資料指南與測試。
    """
    q = data['quotes']; blocks = []
    body = '<div class="index-grid">'
    for key, title in [('sp500', '標普 500 指數'), ('nasdaq', '那斯達克綜合指數'), ('dow', '道瓊工業平均指數')]:
        item = q[key]
        body += f'<article class="index-card"><h3>{title}</h3>'
        body += quote_block(item)
        body += note('解讀', f'{direction(item)}；' + ('依已核實收盤漲跌觀察市場情緒。' if item.get('ok') else '無法據此推定市場情緒。'))
        body += links(item.get('sources', [])) + '</article>'
    body += '</div>' + note('不確定性', '各指數只使用已完成交易日資料，交易時段終點不等於最後一筆成交時間；遇美國休市以實際最新可得日期為準。來源未提供的數據不補值。')
    # 只有三個指數都可確認且同向，才給美股整體一致方向。
    good = [q[k]['change'] for k in ('sp500', 'nasdaq', 'dow') if q[k].get('ok')]
    us = '偏多' if len(good) == 3 and all(v > 0 for v in good) else '偏空' if len(good) == 3 and all(v < 0 for v in good) else '分歧'
    blocks.append(section(1, body, us))
    for n, key, reading, uncertainty in [
        (2, 'tsm', 'ADR 的收盤方向可作為台積電開盤情緒參考，實際仍須觀察台股承接。', 'ADR 與普通股幣別、代表股數及交易時間不同，不直接比較名目股價，也不保證漲跌幅一致。'),
        (3, 'sox', '費半方向反映美國半導體族群當日整體表現，可供台股半導體與電子權值股參考。', '指數表現不代表所有成分股同步，也不能保證台股跟隨。')]:
        item = q[key]
        body = quote_block(item) + note('解讀', reading if item.get('ok') else '資料未確認，暫無方向性判讀。') + note('不確定性', uncertainty) + links(item.get('sources', []))
        blocks.append(section(n, body, direction(item)))
    tx, cash = q['tx'], q['spot']
    body = quote_block(tx)
    if tx.get('ok'):
        body += key_values([('實際月份合約', tx['contract']), ('官方歸屬交易日', tx['date']), ('夜盤起點', tx['session_start']), ('夜盤結束', tx['session_end']), ('夜盤開／高／低', f'{fmt(tx["open"])}／{fmt(tx["high"])}／{fmt(tx["low"])}')])
        body += note('解讀', f'夜盤終值相對開盤{("上漲" if tx["value"] > tx["open"] else "下跌" if tx["value"] < tx["open"] else "持平")}，盤中高低差 {fmt(tx["high"]-tx["low"])} 點；僅憑 OHLC 無法確認高低點先後，不宣稱已形成反轉或穩定區間。')
        if cash.get('ok'):
            gap = tx['value'] - cash['value']
            body += note('事實', f'前日現貨 {cash["date"]} 收盤 {fmt(cash["value"])} 點；期現位置差自行計算：{fmt(tx["value"])} − {fmt(cash["value"])} ＝ {fmt(gap, signed=True)} 點（{fmt(gap/cash["value"]*100,signed=True)}%）。')
        else:
            body += note('不確定性', '前日現貨未確認，無法計算期現位置差。' + cash.get('error', ''))
    body += note('不確定性', '期現貨時點與商品不同，位置差不等於保證開盤缺口。TX1! 為連續合約；此處只採期交所實際月份的盤後交易最後成交價。')
    body += links(tx.get('sources', []) + cash.get('sources', []))
    blocks.append(section(4, body, direction(tx)))
    treasury = q['treasury']
    tr_reading = ('殖利率上升，對科技股估值形成折現率壓力。' if treasury.get('change', 0) > 0 else '殖利率下降，可減輕科技股估值的折現率壓力；仍須辨識經濟風險。' if treasury.get('change', 0) < 0 else '殖利率變動有限，方向性訊號不明。') if treasury.get('ok') else '官方每日值未確認，無法判讀利率方向。'
    body = quote_block(treasury) + note('解讀', tr_reading) + note('不確定性', 'Treasury 為每日公債平價曲線值，並非即時市場殖利率；不混用 ^TNX 的未知縮放單位。') + links(treasury.get('sources', []))
    blocks.append(section(5, body, '官方每日值' if treasury.get('ok') else '資料未確認'))
    dollar = q['dxy']
    dx_reading = ('美元走強，通常對全球風險資金形成壓力，仍須考量背後驅動。' if dollar.get('change', 0) > 0 else '美元走弱，通常可減輕風險資產的資金壓力，仍須交叉驗證。' if dollar.get('change', 0) < 0 else '美元變化有限，訊號不明。') if dollar.get('ok') else '美元最新日期、時間或比較基準未確認，不作強弱推定。'
    body = quote_block(dollar) + note('解讀', dx_reading) + note('不確定性', 'DXY 不等於美元兌新台幣匯率，不能推算新台幣實際升貶幅度；最新快照不標成正式收盤。') + links(dollar.get('sources', []))
    blocks.append(section(6, body, '最新快照' if dollar.get('ok') else '資料未確認'))
    # 利率／美元任一缺漏或兩者不同向，就保留訊號不明。
    environment = '訊號不明'
    if treasury.get('ok') and dollar.get('ok'):
        if treasury['change'] < 0 and dollar['change'] < 0:
            environment = '有利風險偏好'
        elif treasury['change'] > 0 and dollar['change'] > 0:
            environment = '不利風險偏好'
    signals = [('美股整體', us), ('半導體族群', direction(q['sox'])), ('台積電 ADR', direction(q['tsm'])), ('台指期夜盤', direction(tx)), ('利率與美元環境', environment)]
    summary = '<section id="summary" class="market summary"><header class="section-head"><span class="number">Σ</span><div><h2>台股開盤前綜合判讀</h2><p>依已核實資料的合理推論，不保證開盤方向</p></div></header><h3>A. 外部市場訊號 <span class="label-inline">【解讀】</span></h3><div class="signal-grid">'
    summary += ''.join(f'<div><span>{e(k)}</span><b class="{("up" if v == "偏多" else "down" if v == "偏空" else "neutral")}">{e(v)}</b></div>' for k, v in signals) + '</div>'
    summary += '<h3>B. 開盤後三項觀察 <span class="label-inline">【解讀／待驗證】</span></h3><ol class="watch-list"><li><b>台積電是否呼應 ADR 方向</b><p>追蹤開盤與其後承接，避免把 ADR 漲跌幅當作台股應有漲幅。</p></li><li><b>加權指數是否呼應夜盤訊號</b><p>比較前日現貨收盤位置與開盤後是否回吐，期貨點位不等於現貨開盤目標。</p></li><li><b>電子權值與半導體是否同步</b><p>觀察漲跌是否擴散至主要族群，並留意利率與美元環境是否形成反向訊號。</p></li></ol><h3>C. 綜合結論 <span class="label-inline">【解讀】</span></h3>'
    positives = [k for k, v in signals[:4] if v == '偏多']; negatives = [k for k, v in signals[:4] if v == '偏空']
    overall = '偏多' if len(positives) == 4 else '偏空' if len(negatives) == 4 else '訊號分歧或資料不足'
    conclusion = f'外部市場整體{overall}。正向支持為{("、".join(positives) or "尚無足夠已確認指標")}；反向訊號為{("、".join(negatives) or "主要股市指標未見一致反向訊號")}，利率與美元環境為{environment}。開盤後優先觀察台積電、加權指數與電子族群的方向及延續性。來源延遲、缺漏與期現時間差仍造成不確定性，應以各節實際日期及狀態為準。'
    summary += '<div class="conclusion"><p>' + e(conclusion) + '</p></div></section>'
    blocks.append(summary)
    blocks.append('<section id="audit" class="market audit"><header class="section-head"><span class="number">i</span><div><h2>資料狀態與查核範圍</h2></div></header>' + note('事實', data['gate']['reason'] + '；已查官方新聞清單，未見需人工判讀的交易異動公告。') + note('不確定性', '官方清單可能有更新延遲；公告判讀採保守門檻。來源失敗保留缺漏，不以舊行情冒充新數字。判讀為固定規則的資料觀察，沒有捏造新聞或事件。') + links([data['gate']['calendar_url'], data['gate']['notice_url']]) + '</section>')
    meta = key_values([('報告日期／交易狀態', data['date'] + ' · 正常交易日'), ('原訂排程時間', '每日 08:30 · Asia/Taipei'), ('實際產出時間', data['generated_at']), ('資料截止時間', data['cutoff'])])
    missing = [k for k, v in q.items() if not v.get('ok')]
    late = data['generated_at'][11:16] >= '09:00'
    alert = ('已逾 09:00 開盤時間，本報告不是 08:30 已完成的預測。' if late else '各市場資料時點不同，請依日期與交易狀態閱讀。')
    if missing:
        alert += f' {len(missing)} 項來源資料未確認，詳見各節。'
    return meta + '<div class="alert"><b>' + e(alert) + '</b>資料只在排程執行時更新，開啟頁面不會混入新行情。</div>' + ''.join(blocks)


def page(content, title, assets='assets', is_index=False):
    """包裝完整頁面；content 必須是本程式產生的可信 HTML 片段。

    is_index 決定能否載入歷史清單，assets 處理首頁與獨立歷史頁的相對路徑。
    這裡不能接任意外部 HTML，也不能將整段 content 跳脫成純文字。
    """
    nav = ''.join(f'<a href="#market-{i}"><span>{i:02}</span>{e(name)}</a>' for i, (name, _) in enumerate(NAMES, 1))
    nav += '<a href="#summary"><span>Σ</span>綜合判讀</a><a href="#audit"><span>i</span>資料查核範圍</a>'
    root = '' if is_index else '../'
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{e(title)}｜PMOT</title><link rel="stylesheet" href="{assets}/report.css"><link rel="icon" type="image/svg+xml" href="{assets}/favicon.svg"></head><body id="top" data-index="{str(is_index).lower()}"><div class="layout"><aside class="sidebar"><div class="brand"><span class="brand-mark">P</span>市場觀察筆記</div><div><p class="sidebar-label">台股交易日 · 08:30 更新</p><nav aria-label="報告章節">{nav}</nav></div><div class="sidebar-bottom">台股開盤前的外部市場訊號<br>保留每一項數據的實際時點。<a href="{root}prompt.md">檢視完整 prompt ↗</a><a href="https://github.com/cjw9223233/PMOT" target="_blank" rel="noopener noreferrer">GitHub 專案 ↗</a></div></aside><main class="content"><p class="eyebrow">TAIWAN MARKET · MORNING OBSERVATION</p><h1>台股開盤前<span>外部市場觀察報告</span></h1><p class="intro">美股、ADR、半導體、台指期、利率與美元；依實際交易時點檢視市場訊號。</p><div class="toolbar"><label for="report-picker">報告日期</label><select id="report-picker" aria-label="切換歷史報告"><option>載入報告清單…</option></select><button class="button primary" type="button" id="print-report">列印／另存 PDF</button><a class="button" href="{root}prompt.md">查看 prompt</a></div><p id="site-status" class="site-status" role="status">台股交易日 08:30 觸發更新；實際產出時間以報告為準。</p><div id="report-content">{content}</div><footer class="footer"><p>【事實】來源確認資料　【解讀】合理推論　【不確定性】缺漏、衝突或待驗證事項</p><p>本報告是市場觀察工具，不是保證行情方向的預測，也不是個別股票的買賣建議。</p><p>紅色表示上漲、綠色表示下跌，並保留正負號。休市日保留最近一份報告。</p></footer></main></div><a class="button back-top" href="#top">↑ 回頂端</a><script src="{assets}/app.js" defer></script></body></html>'''


def build_index(site):
    """以現有清單第一筆片段重建首頁，不查新行情、不重算報告內文。

    不自行排序清單，維護者可用這個特性回復舊報告；空清單或缺檔會失敗。
    """
    manifest = site / 'data' / 'reports.json'
    entries = json.loads(manifest.read_text(encoding='utf-8'))
    if not entries:
        raise ValueError('No report available to publish')
    latest = entries[0]
    content = (site / latest['content']).read_text(encoding='utf-8')
    # 片段已由本程式格式化與跳脫；讀取歷史檔不會重新抓取或重算行情。
    (site / 'index.html').write_text(page(content, latest['date'] + ' 台股開盤前觀察', is_index=True), encoding='utf-8')


def publish(data, site):
    """依台北 ISO 產出時間命名，寫內容、完整頁、JSON、清單，再重建首頁。

    現行防重複檢查是內容片段路徑；尚未對所有產物作交易式提交。
    若中途 I/O 失敗，可能留下孤立檔或不同步的清單，需依維運手冊檢查恢復。
    """
    stamp = data['generated_at'].replace('-', '').replace(':', '')[:15].replace('T', '_')
    stem = data['date'] + '_' + data['generated_at'][11:19].replace(':', '')
    content = render_report(data)
    for folder in ('reports', 'data'):
        (site / folder).mkdir(parents=True, exist_ok=True)
    content_path = f'data/{stem}.html'
    report_path = f'reports/{stem}.html'
    # 防止同一秒的識別字重複；後續各次寫檔仍可能失敗，尚無整批回滾。
    if (site / content_path).exists():
        raise FileExistsError('Report timestamp already exists')
    (site / content_path).write_text(content, encoding='utf-8')
    (site / report_path).write_text(page(content, data['date'], assets='../assets'), encoding='utf-8')
    (site / 'data' / f'{stem}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = site / 'data' / 'reports.json'
    entries = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
    entries.insert(0, {'date': data['date'], 'generated_at': data['generated_at'], 'content': content_path, 'path': report_path, 'status': 'partial' if any(not v.get('ok') for v in data['quotes'].values()) else 'verified'})
    # 發布新報告時才排序；單獨 build_index() 會尊重清單原本第一筆。
    entries.sort(key=lambda x: x['generated_at'], reverse=True)
    manifest.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')
    build_index(site)
