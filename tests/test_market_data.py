"""用合成資料測試邊界條件，不把測試數字當真實市場報價。

TestCase 的 test_* 會由 unittest 自動發現；固定 NOW 讓測試不隨今日時間變動。
patch 替換外部判斷，TemporaryDirectory 隔離寫檔，測試不需要抓真實行情。
"""
from datetime import datetime, date, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

from pmot.sources import TAIPEI, NEW_YORK, number, parse_calendar, parse_date, parse_yahoo, parse_dxy, parse_treasury, parse_tx, check_notices, parse_tsm_history
from pmot.render import page, render_report, publish

NOW = datetime(2026, 11, 4, 8, 30, tzinfo=TAIPEI)


def timestamp(y, m, d, hour=9, minute=30):
    """由美東日期建立 Unix 秒數，讓 fixture 經過與真實行情相同的時區轉換。"""
    return int(datetime(y, m, d, hour, minute, tzinfo=NEW_YORK).timestamp())


def chart(symbol='TSM'):
    """建立最小 Yahoo chart 合成回應；100／104 只用來驗算 4% 的公式。"""
    return {'chart': {'result': [{'meta': {'symbol': symbol, 'currency': 'USD', 'regularMarketTime': timestamp(2026, 11, 3, 16, 0), 'regularMarketPrice': 104}, 'timestamp': [timestamp(2026, 11, 2), timestamp(2026, 11, 3)], 'indicators': {'quote': [{'close': [100, 104]}]}}]}}


def night_html(session='2026/11/03 15:00~次日05:00 盤後交易時段行情表', official='2026/11/04'):
    """同時放單式與價差合約，檢驗解析器能排除價差，不只是讀到任意一列 TX。"""
    return f'<p>日期：{official}</p><p>{session}</p><table><tr><td>TX</td><td>202611</td><td>100</td><td>106</td><td>98</td><td>104</td><td>▲4</td><td>▲4.00%</td><td>10</td><td>-</td></tr><tr><td>TX</td><td>202611/202612</td><td>2</td><td>3</td><td>1</td><td>2</td><td>1</td><td>1%</td><td>4</td></tr></table>'


class CalendarTests(TestCase):
    """保護正常開市註記、休市、年度切換與公告保守門檻。"""
    def payload(self):
        return {'stat': 'ok', 'data': [[f'2026-01-{d:02}', '假日', ''] for d in range(1, 11)] + [['2026-02-11', '農曆春節前最後交易日', ''], ['2026-02-23', '農曆春節後開始交易日', '']]}

    def test_normal_weekday(self):
        self.assertTrue(parse_calendar(self.payload(), date(2026, 11, 4))[0])

    def test_weekend(self):
        self.assertFalse(parse_calendar(self.payload(), date(2026, 11, 7))[0])

    def test_holiday_and_explicit_open_annotation(self):
        self.assertFalse(parse_calendar(self.payload(), date(2026, 1, 1))[0])
        self.assertTrue(parse_calendar(self.payload(), date(2026, 2, 11))[0])
        self.assertTrue(parse_calendar(self.payload(), date(2026, 2, 23))[0])

    def test_wrong_year_or_empty_calendar_fails(self):
        with self.assertRaises(ValueError): parse_calendar(self.payload(), date(2027, 11, 4))
        with self.assertRaises(ValueError): parse_calendar({'stat': 'ok', 'data': []}, date(2026, 11, 4))

    def test_roc_dates(self):
        self.assertEqual(parse_date('1151103'), date(2026, 11, 3))
        self.assertEqual(parse_date('115/11/03'), date(2026, 11, 3))

    def test_stale_notice_list_rejected(self):
        with self.assertRaises(ValueError): check_notices([{'Date':'1150101','Title':'公告'}], NOW.date(), None)

    def test_closure_notice_requires_manual_review(self):
        class Fake:
            def text(self, url): return '<p>2026年11月4日因颱風集中市場休市</p>'
        result, _ = check_notices([{'Date':'1151104','Title':'颱風休市公告','Url':'https://www.twse.com.tw/notice'}], NOW.date(), Fake())
        self.assertFalse(result)


class QuoteTests(TestCase):
    """保護商品、完成日線、DST、DXY 基準及 ADR 備援，拒收過期或未來時間。"""
    def test_numeric_units_and_signs(self):
        self.assertEqual(number('▼-286'), -286)
        self.assertEqual(number('▲1,234.50%'), 1234.5)
        for invalid in [None, '-', 'nan', float('inf'), True]:
            with self.assertRaises((ValueError, TypeError)): number(invalid)

    def test_completed_close_and_actual_prior_date(self):
        r = parse_yahoo(chart(), 'TSM', NOW)
        self.assertEqual(r['value'], 104)
        self.assertAlmostEqual(r['percent'], 4)
        self.assertEqual(r['previous_date'], '2026-11-02')

    def test_unfinished_day_not_accepted_as_close(self):
        during = datetime(2026, 11, 3, 12, tzinfo=NEW_YORK)
        with self.assertRaises(ValueError): parse_yahoo(chart(), 'TSM', during)

    def test_symbol_mismatch_and_stale_close_rejected(self):
        with self.assertRaises(ValueError): parse_yahoo(chart(), '^GSPC', NOW)
        with self.assertRaises(ValueError): parse_yahoo(chart(), 'TSM', datetime(2026, 11, 15, 8, 30, tzinfo=TAIPEI))

    def test_new_york_dst_is_not_fixed_utc_offset(self):
        self.assertEqual(datetime(2026, 7, 1, 16, tzinfo=NEW_YORK).astimezone(TAIPEI).hour, 4)
        self.assertEqual(datetime(2026, 11, 3, 16, tzinfo=NEW_YORK).astimezone(TAIPEI).hour, 5)

    def test_dxy_uses_previous_dated_bar_not_range_base(self):
        c = chart('DX-Y.NYB');m=c['chart']['result'][0]['meta'];m['chartPreviousClose']=80;m['regularMarketPrice']=104
        r=parse_dxy(c,NOW)
        self.assertEqual(r['previous'],100)
        self.assertEqual(r['change'],4)

    def test_dxy_future_timestamp_rejected(self):
        c=chart('DX-Y.NYB');c['chart']['result'][0]['meta']['regularMarketTime']=timestamp(2026,11,4,16)
        with self.assertRaises(ValueError): parse_dxy(c,NOW)

    def test_tsm_backup_uses_unadjusted_close_not_after_hours(self):
        text='<p>NYSE: TSM USD After-hours 999</p><table><tr><td>Nov 3, 2026</td><td>100</td><td>110</td><td>99</td><td>104</td><td>102</td><td>4%</td><td>10</td></tr><tr><td>Nov 2, 2026</td><td>99</td><td>101</td><td>98</td><td>100</td><td>98</td><td>1%</td><td>10</td></tr></table>'
        r=parse_tsm_history(text,NOW)
        self.assertEqual(r['value'],104)
        self.assertEqual(r['previous'],100)
        self.assertAlmostEqual(r['percent'],4)


class FuturesAndYieldTests(TestCase):
    """保護夜盤歸屬／實際結束日及殖利率單位，避免看似合理但口徑錯誤的數字。"""
    def test_night_session_uses_actual_contract_not_spread(self):
        r=parse_tx(night_html(),NOW)
        self.assertEqual(r['contract'],'202611')
        self.assertEqual(r['value'],104)
        self.assertEqual(r['session_end'],'2026-11-04T05:00:00+08:00')

    def test_day_session_and_wrong_trading_date_rejected(self):
        with self.assertRaises(ValueError):parse_tx(night_html(session='一般交易時段行情表'),NOW)
        with self.assertRaises(ValueError):parse_tx(night_html(official='2026/11/03'),NOW)

    def test_unfinished_night_rejected(self):
        with self.assertRaises(ValueError):parse_tx(night_html(),datetime(2026,11,4,4,tzinfo=TAIPEI))

    def test_monday_ownership_does_not_change_saturday_end_date(self):
        r=parse_tx(night_html(session='2026/10/30 15:00~次日05:00 盤後交易時段行情表',official='2026/11/02'),datetime(2026,11,2,8,30,tzinfo=TAIPEI))
        self.assertTrue(r['session_end'].startswith('2026-10-31'))

    def test_treasury_percent_points_convert_to_basis_points(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"><entry><d:NEW_DATE>2026-11-02T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.91</d:BC_10YEAR></entry><entry><d:NEW_DATE>2026-11-03T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.95</d:BC_10YEAR></entry></feed>'''
        r=parse_treasury(xml,NOW)
        self.assertAlmostEqual(r['basis_points'],4)
        self.assertEqual(r['value'],4.95)


class PublicationTests(TestCase):
    """保護缺值顯示、HTML 跳脫、歷史防重複與不應發布時保留舊首頁。"""
    def data(self):
        """製作全部缺漏的完整報告結構；error 故意含 script，測試顯示時會跳脫。"""
        missing={'ok':False,'error':'來源未更新 <script>alert(1)</script>','sources':['https://example.com/']}
        return {'date':'2026-11-04','scheduled_time':'08:30 Asia/Taipei','generated_at':'2026-11-04T08:35:00+08:00','cutoff':'2026-11-04T08:34:58+08:00','gate':{'reason':'官方行事曆','calendar_url':'https://www.twse.com.tw/','notice_url':'https://openapi.twse.com.tw/'},'quotes':{k:dict(missing) for k in ['sp500','nasdaq','dow','tsm','sox','tx','spot','treasury','dxy']}}

    def test_missing_data_is_not_a_bullish_signal_or_html_injection(self):
        s=render_report(self.data())
        self.assertIn('分歧（資料不足）',s)
        self.assertNotIn('<script>alert(1)</script>',s)
        self.assertIn('&lt;script&gt;',s)

    def test_all_sections_and_real_timestamp_present(self):
        s=render_report(self.data())
        for i in range(1,7):self.assertIn(f'id="market-{i}"',s)
        self.assertIn('08:35:00',s)
        self.assertIn('08:30',s)

    def test_history_is_immutable_and_index_uses_actual_report(self):
        with TemporaryDirectory() as d:
            site=Path(d);publish(self.data(),site)
            self.assertIn('08:35:00',(site/'index.html').read_text(encoding='utf-8'))
            index=json.loads((site/'data'/'reports.json').read_text(encoding='utf-8'))
            self.assertEqual(len(index),1)
            with self.assertRaises(FileExistsError):publish(self.data(),site)

    def test_new_schedule_and_late_notice_use_recorded_clock(self):
        """變更排程只改新報告；實際完成時間與當次原訂時間分開保留。"""
        data=self.data()
        data['scheduled_time']='08:00 Asia/Taipei'
        data['generated_at']='2026-11-04T09:05:00+08:00'
        s=render_report(data)
        self.assertIn('每日 08:00',s)
        self.assertIn('不是 08:00 已完成的預測',s)
        self.assertIn('09:05:00',s)
        self.assertNotIn('08:30',s)

    def test_closed_day_does_not_touch_existing_index(self):
        from pmot.__main__ import update
        with TemporaryDirectory() as d:
            p=Path(d);(p/'index.html').write_text('previous good report',encoding='utf-8')
            with patch('pmot.__main__.trading_day',return_value={'open':False,'reason':'休市'}):
                self.assertFalse(update(p,NOW,object()))
            self.assertEqual((p/'index.html').read_text(encoding='utf-8'),'previous good report')

    def test_calendar_failure_does_not_publish(self):
        from pmot.__main__ import update
        with TemporaryDirectory() as d:
            p=Path(d);(p/'index.html').write_text('keep',encoding='utf-8')
            with patch('pmot.__main__.trading_day',side_effect=ValueError('calendar unavailable')):
                with self.assertRaises(ValueError): update(p,NOW,object())
            self.assertEqual((p/'index.html').read_text(encoding='utf-8'),'keep')
