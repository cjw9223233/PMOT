"""Source-specific parsers. A missing or inconsistent value remains missing."""
from datetime import datetime, date, time, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo
import json
import math
import re
import xml.etree.ElementTree as ET

TAIPEI = ZoneInfo('Asia/Taipei')
NEW_YORK = ZoneInfo('America/New_York')
CALENDAR = 'https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule'
NEWS = 'https://openapi.twse.com.tw/v1/news/newsList'
TX_URL = 'https://www.taifex.com.tw/cht/3/futDailyMarketReport'
TREASURY = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('Missing numeric value')
    if isinstance(value, str):
        value = value.strip().replace(',', '').replace('%', '').replace('▲', '').replace('▼', '-').replace('−', '-').replace('--', '-')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite numeric value')
    return result


def parse_date(value):
    s = str(value).strip()
    if re.fullmatch(r'\d{7}', s):
        return date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:]))
    match = re.fullmatch(r'(\d{3,4})[年/-](\d{1,2})[月/-](\d{1,2})日?', s)
    if not match:
        raise ValueError('Unknown date format: ' + s)
    y, m, d = map(int, match.groups())
    return date(y + 1911 if y < 1911 else y, m, d)


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.words, self.row, self.cell = [], [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th') and self.row is not None:
            self.cell = []
        if tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_data(self, data):
        self.words.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def parse_calendar(payload, today):
    if payload.get('stat') != 'ok' or not payload.get('data'):
        raise ValueError('Official holiday calendar unavailable')
    rows = payload['data']
    dates = [parse_date(r[0]) for r in rows]
    if any(d.year != today.year for d in dates) or len(dates) < 10:
        raise ValueError('Calendar year or completeness not confirmed')
    if today.weekday() >= 5:
        return False, '週末'
    for row in rows:
        if parse_date(row[0]) == today:
            title = row[1]
            # These are open-day annotations in the official calendar.
            if '開始交易日' in title or '最後交易日' in title:
                return True, title
            return False, title
    return True, 'TWSE 當年度行事曆未列休市'


def check_notices(payload, today, fetch):
    if not isinstance(payload, list) or not payload:
        raise ValueError('TWSE notice list unavailable')
    dated = [(parse_date(x['Date']), x) for x in payload if x.get('Date')]
    if not dated or max(d for d, _ in dated) < today - timedelta(days=7):
        raise ValueError('TWSE notice list is stale')
    scanned = []
    for issued, item in dated:
        if not today - timedelta(days=7) <= issued <= today:
            continue
        title = item.get('Title', '')
        if not re.search(r'休市|停止交易|延後開盤|延遲開盤|颱風|天然災害', title):
            continue
        # Read potentially relevant announcements; never guess the affected date.
        url = item['Url']
        if not url.startswith('https://www.twse.com.tw/'):
            raise ValueError('Untrusted official notice link')
        body = fetch.text(url)
        parser = Tables(); parser.feed(body)
        body = ' '.join(parser.words)
        scanned.append({'title': title, 'url': url, 'issued': issued.isoformat()})
        # An exchange-wide exception needs human interpretation; suppress a normal report.
        if not ('不休市' in title or '照常交易' in title):
            return False, scanned
    return True, scanned


def trading_day(fetch, now):
    today = now.astimezone(TAIPEI).date()
    url = CALENDAR + '?' + urlencode({'response': 'json', 'queryYear': today.year - 1911})
    opened, reason = parse_calendar(fetch.json(url), today)
    result = {'open': opened, 'reason': reason, 'calendar_url': url, 'notice_url': NEWS}
    if not opened:
        return result
    normal, scanned = check_notices(fetch.json(NEWS), today, fetch)
    result['scanned_notices'] = scanned
    if not normal:
        raise ValueError('近期存在休市或交易異動公告，無法自動確認當日正常交易；保留上一份報告')
    return result


def parse_yahoo(payload, symbol, now, is_index=False):
    items = payload.get('chart', {}).get('result')
    if not items:
        raise ValueError('Yahoo chart has no result')
    item = items[0]
    if item.get('meta', {}).get('symbol') != symbol:
        raise ValueError('Quote symbol mismatch')
    closes = item['indicators']['quote'][0]['close']
    tz = NEW_YORK
    bars = []
    for timestamp, value in zip(item.get('timestamp', []), closes):
        if value is None:
            continue
        d = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(tz).date()
        session_end = datetime.combine(d, time(16), tzinfo=tz)
        # Do not label an unfinished daily bar a closing price.
        if session_end + timedelta(minutes=10) <= now.astimezone(tz):
            bars.append((d, number(value)))
    bars = sorted(dict(bars).items())
    if len(bars) < 2:
        raise ValueError('Two completed sessions not available')
    (previous_date, previous), (d, value) = bars[-2:]
    if previous <= 0 or value <= 0 or (now.astimezone(tz).date() - d).days > 4:
        raise ValueError('Invalid or stale close')
    # The quote endpoint must also identify this as the latest regular session.
    meta = item['meta']
    market_time = datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).astimezone(tz)
    if market_time.date() != d or market_time > now:
        raise ValueError(f'Latest regular session {market_time.isoformat()} does not match daily close {d}')
    return {'ok': True, 'symbol': symbol, 'value': value, 'previous': previous, 'previous_date': previous_date.isoformat(), 'date': d.isoformat(), 'change': value - previous, 'percent': (value / previous - 1) * 100, 'unit': '點' if is_index else meta.get('currency', 'USD'), 'time': f'{market_time.isoformat()}（來源常規行情最後更新，非保證最後一筆成交時間）', 'status': '已完成交易日收盤；日線資料，非盤後', 'calculation': '漲跌自行計算：本日收盤 − 前日收盤；漲跌幅＝差額 ÷ 前日收盤 × 100。交易所最後一筆成交時分未另提供；不假定提早收盤日也在 16:00 收盤。'}


def yahoo_close(fetch, symbol, now, is_index=False):
    failures = []
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url = f'https://{host}/v8/finance/chart/{quote(symbol, safe="")}?range=1mo&interval=1d'
        try:
            data = parse_yahoo(fetch.json(url), symbol, now, is_index)
            data['sources'] = [url, f'https://finance.yahoo.com/quote/{quote(symbol, safe="")}/']
            return data
        except Exception as exc:
            failures.append(str(exc))
    if symbol == 'TSM':
        url = 'https://stockanalysis.com/stocks/tsm/history/'
        try:
            data = parse_tsm_history(fetch.text(url), now)
            data['sources'] = [url, 'https://finance.yahoo.com/quote/TSM/']
            data['calculation'] += ' Yahoo 的常規行情日期與日線不一致，本次改採日期別歷史表。'
            return data
        except Exception as exc:
            failures.append('Stock Analysis: ' + str(exc))
    raise ValueError('Yahoo 兩個行情端點均未確認：' + '；'.join(failures))


def parse_tsm_history(text, now):
    table = Tables(); table.feed(text)
    if 'USD' not in ' '.join(table.words):
        raise ValueError('TSM currency not confirmed')
    rows = []
    for row in table.rows:
        if len(row) < 8:
            continue
        try:
            d = datetime.strptime(row[0], '%b %d, %Y').date()
        except ValueError:
            continue
        if datetime.combine(d, time(16), NEW_YORK) + timedelta(minutes=10) <= now:
            rows.append((d, number(row[4])))
    rows = sorted(dict(rows).items())
    if len(rows) < 2:
        raise ValueError('Two completed TSM historical closes unavailable')
    (prior, previous), (d, value) = rows[-2:]
    if previous <= 0 or value <= 0 or (now.astimezone(NEW_YORK).date() - d).days > 4:
        raise ValueError('TSM historical closes are stale or invalid')
    return {'ok': True, 'symbol': 'TSM', 'value': value, 'previous': previous, 'previous_date': prior.isoformat(), 'date': d.isoformat(), 'change': value - previous, 'percent': (value / previous - 1) * 100, 'unit': 'USD', 'time': f'{d}（美東交易日；日期別正式收盤，精確更新時分未提供）', 'status': 'Stock Analysis 歷史表 Close 欄；不採 Adj. Close 或盤後價格', 'calculation': '漲跌與百分比自行計算，以同一歷史表的前一交易日未調整 Close 為基準。'}


def parse_dxy(payload, now):
    item = payload['chart']['result'][0]
    m = item['meta']
    if m['symbol'] != 'DX-Y.NYB':
        raise ValueError('DXY instrument mismatch')
    value = number(m['regularMarketPrice'])
    # chartPreviousClose is the beginning of a requested range, NOT always previous day.
    # Use daily bars to select the actual preceding dated session instead.
    quote_date = datetime.fromtimestamp(m['regularMarketTime'], timezone.utc).astimezone(NEW_YORK).date()
    quote_time = datetime.fromtimestamp(m['regularMarketTime'], timezone.utc)
    bars = [(datetime.fromtimestamp(t, timezone.utc).astimezone(NEW_YORK).date(), number(v)) for t, v in zip(item['timestamp'], item['indicators']['quote'][0]['close']) if v is not None]
    previous_bars = [(d, v) for d, v in bars if d < quote_date]
    if not previous_bars or quote_time > now or now - quote_time > timedelta(hours=30):
        raise ValueError('DXY quote timestamp or preceding session not confirmed')
    prior_date, previous = max(previous_bars)
    if value <= 0 or previous <= 0:
        raise ValueError('Invalid DXY value')
    return {'ok': True, 'symbol': 'DX-Y.NYB', 'value': value, 'previous': previous, 'previous_date': prior_date.isoformat(), 'date': quote_date.isoformat(), 'time': quote_time.astimezone(TAIPEI).isoformat(), 'change': value - previous, 'percent': (value / previous - 1) * 100, 'unit': '點', 'status': '最新行情快照；來源延遲狀態未確認，非正式收盤', 'calculation': '自行計算，以同來源上一個日期別收盤為比較基準。'}


def dxy(fetch, now):
    errors = []
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url = f'https://{host}/v8/finance/chart/DX-Y.NYB?range=1mo&interval=1d'
        try:
            r = parse_dxy(fetch.json(url), now); r['sources'] = [url, 'https://www.tradingview.com/symbols/TVC-DXY/', 'https://finance.yahoo.com/quote/DX-Y.NYB/']; return r
        except Exception as exc:
            errors.append(str(exc))
    raise ValueError('美元最新日期與基準無法確認：' + '；'.join(errors))


def parse_treasury(xml, now):
    root = ET.fromstring(xml)
    records = []
    for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
        record = {e.tag.split('}')[-1]: e.text for e in entry.iter()}
        if record.get('BC_10YEAR') and record.get('NEW_DATE'):
            d = date.fromisoformat(record['NEW_DATE'][:10])
            if d <= now.astimezone(NEW_YORK).date():
                records.append((d, number(record['BC_10YEAR'])))
    records = sorted(dict(records).items())
    if len(records) < 2:
        raise ValueError('Two official daily Treasury observations unavailable')
    (prior, previous), (d, value) = records[-2:]
    if (now.astimezone(NEW_YORK).date() - d).days > 5:
        raise ValueError('Treasury daily data stale')
    return {'ok': True, 'symbol': 'US 10Y', 'value': value, 'previous': previous, 'date': d.isoformat(), 'previous_date': prior.isoformat(), 'change': value - previous, 'basis_points': (value - previous) * 100, 'unit': '%', 'time': '官方每日值；精確發布時分未提供', 'status': 'Treasury 10 Yr Par Yield Curve；非即時在券殖利率', 'calculation': '自行計算：百分點差 × 100 ＝ 基點。採官方百分比單位，未對未取得的 ^TNX 做乘除 10 換算。'}


def treasury(fetch, now):
    year = now.astimezone(NEW_YORK).year
    url = TREASURY + '?' + urlencode({'data': 'daily_treasury_yield_curve', 'field_tdr_date_value': year})
    xml = fetch.text(url)
    if now.month == 1:
        prior = TREASURY + '?' + urlencode({'data': 'daily_treasury_yield_curve', 'field_tdr_date_value': year - 1})
        # Merge entries at the year boundary, keeping the current year's feed identity.
        a, b = ET.fromstring(xml), ET.fromstring(fetch.text(prior))
        a.extend(b.findall('{http://www.w3.org/2005/Atom}entry'))
        xml = ET.tostring(a, encoding='unicode')
    r = parse_treasury(xml, now); r['sources'] = [url, 'https://finance.yahoo.com/quote/%5ETNX/']; return r


def parse_tx(text, now):
    table = Tables(); table.feed(text)
    words = ' '.join(table.words)
    today = now.astimezone(TAIPEI).date()
    dates = re.findall(r'日期[：:]\s*(\d{4}/\d{1,2}/\d{1,2})', words)
    if not dates or parse_date(dates[-1]) != today:
        raise ValueError('TX official trading date not current')
    session = re.search(r'(\d{4}/\d{1,2}/\d{1,2})\s+15:00\s*[~～至]\s*次日\s*05:00\s*盤後交易時段', words)
    if not session:
        raise ValueError('Not a confirmed after-hours session (day-session data rejected)')
    start_date = parse_date(session[1])
    end = datetime.combine(start_date + timedelta(days=1), time(5), TAIPEI)
    if end > now or (today - end.date()).days > 4:
        raise ValueError('TX night session incomplete or stale')
    candidates = [r for r in table.rows if len(r) >= 9 and r[0] == 'TX' and re.fullmatch(r'\d{6}', r[1]) and r[1] >= today.strftime('%Y%m') and r[5] != '-']
    if not candidates:
        raise ValueError('No outright near-month TX contract found')
    row = min(candidates, key=lambda r: r[1])
    opened, high, low, close, change, pct = map(number, row[2:8])
    if not 0 < low <= min(opened, close) <= max(opened, close) <= high:
        raise ValueError('TX OHLC inconsistency')
    return {'ok': True, 'symbol': 'TX', 'contract': row[1], 'value': close, 'change': change, 'percent': pct, 'open': opened, 'high': high, 'low': low, 'date': today.isoformat(), 'session_start': f'{start_date} 15:00 +08:00', 'session_end': end.isoformat(), 'time': end.isoformat(), 'unit': '點', 'status': '已結束的盤後交易時段；官方最後成交價，非結算價', 'calculation': '漲跌與百分比採期交所原欄位；比較基準定義未另行核實。最後一筆成交時分未提供，夜盤結束時間不等於最後成交時間。'}


def tx(fetch, now):
    url = TX_URL + '?' + urlencode({'queryType': '2', 'marketCode': '1', 'commodity_id': 'TX', 'queryDate': now.astimezone(TAIPEI).strftime('%Y/%m/%d')})
    r = parse_tx(fetch.text(url), now); r['sources'] = [url, 'https://www.tradingview.com/symbols/TAIFEX-TX1!/']; return r


def spot(fetch, now):
    url = 'https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK'
    rows = fetch.json(url)
    today = now.astimezone(TAIPEI).date()
    candidates = [(parse_date(r['Date']), number(r['TAIEX'])) for r in rows if parse_date(r['Date']) < today]
    if not candidates:
        raise ValueError('Prior TWSE cash close unavailable')
    d, value = max(candidates)
    if (today - d).days > 5:
        raise ValueError('Prior cash close stale')
    return {'ok': True, 'date': d.isoformat(), 'value': value, 'sources': [url]}
