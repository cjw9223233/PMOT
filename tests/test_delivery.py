"""交付失敗恢復測試：合成檔案，不抓真行情、不真的部署。"""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os

from pmot.delivery import prepare, report_identity, write_json, main
from pmot.sources import TAIPEI

NOW = datetime(2026, 11, 11, 8, 17, tzinfo=TAIPEI)


class DeliveryTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'GITHUB_OUTPUT': '', 'GITHUB_STEP_SUMMARY': ''})
        env.start()
        self.addCleanup(env.stop)
        self.root = Path(self.temp.name)
        self.site = self.root / 'site'
        self.receipt = self.root / '.pmot/deployment.json'
        self.gate = patch('pmot.delivery.trading_day', return_value={'open': True})
        self.gate.start()
        self.addCleanup(self.gate.stop)

    def snapshot(self, day='2026-11-11'):
        entry = {'date': day, 'generated_at': day + 'T08:01:00+08:00',
                 'content': 'data/report.html', 'path': 'reports/report.html', 'status': 'verified'}
        write_json(self.site / 'data/reports.json', [entry])
        write_json(self.site / 'data/report.json', {'synthetic': True})
        for name in ('data/report.html', 'reports/report.html'):
            path = self.site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('<p>synthetic snapshot</p>', encoding='utf-8')
        return entry

    def decide(self, event='schedule'):
        return prepare(self.site, self.receipt, NOW, event, object())[0]

    def test_no_report_generates_but_yesterday_is_not_reused(self):
        self.assertEqual(self.decide(), 'generate')
        self.snapshot('2026-11-10')
        self.assertEqual(self.decide(), 'generate')

    def test_report_without_receipt_retries_without_mutating_snapshot(self):
        entry = self.snapshot()
        before = (self.site / entry['content']).read_bytes()
        self.assertEqual(self.decide(), 'deploy')
        self.assertEqual(self.decide(), 'deploy')  # 前次部署失敗，補跑仍可恢復。
        self.assertEqual((self.site / entry['content']).read_bytes(), before)
        self.assertEqual(len(json.loads((self.site / 'data/reports.json').read_text(encoding='utf-8'))), 1)

    def test_success_receipt_skips_repeated_runs(self):
        entry = self.snapshot()
        self.decide()
        write_json(self.receipt, {'status': 'success', 'report': report_identity(self.site, entry)})
        self.assertEqual(self.decide(), 'skip')
        self.assertEqual(self.decide('workflow_dispatch'), 'skip')
        self.assertEqual(self.decide('push'), 'deploy')

    def test_failed_or_mismatched_receipt_retries(self):
        entry = self.snapshot()
        self.decide()
        identity = report_identity(self.site, entry)
        write_json(self.receipt, {'status': 'pending', 'report': identity})
        self.assertEqual(self.decide(), 'deploy')
        identity['sha256'] = 'wrong'
        write_json(self.receipt, {'status': 'success', 'report': identity})
        self.assertEqual(self.decide(), 'deploy')

    def test_asset_change_requires_redeployment(self):
        entry = self.snapshot()
        self.decide()
        write_json(self.receipt, {'status': 'success', 'report': report_identity(self.site, entry)})
        (self.site / 'assets').mkdir()
        (self.site / 'assets/app.js').write_text('changed')
        self.assertEqual(self.decide(), 'deploy')

    def test_closed_or_unconfirmed_day_does_not_package(self):
        with patch('pmot.delivery.trading_day', return_value={'open': False, 'reason': '休市'}):
            self.assertEqual(self.decide(), 'skip')
        with patch('pmot.delivery.trading_day', side_effect=ValueError('unconfirmed')):
            with self.assertRaises(ValueError): self.decide()
        self.assertFalse(self.site.exists())

    def test_missing_snapshot_fails_instead_of_skipping(self):
        self.snapshot()
        (self.site / 'data/report.json').unlink()
        with self.assertRaises(FileNotFoundError): self.decide()

    def test_package_pending_then_confirm_success_with_real_times(self):
        self.snapshot()
        self.decide()
        timing = self.root / 'timing.json'
        write_json(timing, {'run_id': '123', 'run_attempt': '1', 'run_url': 'https://example.com/'})
        args = ['delivery', 'package', '--site', str(self.site), '--receipt', str(self.receipt), '--timing', str(timing)]
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}), patch('sys.argv', args):
            main()
            pending = json.loads(timing.read_text(encoding='utf-8'))
            self.assertEqual(pending['status'], 'pending')
            self.assertNotIn('deployment_completed_at', pending)
            self.assertFalse(self.receipt.exists())
            args[1] = 'confirm'
            main()
            success = json.loads(self.receipt.read_text(encoding='utf-8'))
            self.assertEqual(success['status'], 'success')
            self.assertGreaterEqual(success['deployment_completed_at'], pending['deployment_requested_at'])
        self.assertEqual(self.decide(), 'skip')

    def test_cannot_confirm_other_run_or_changed_report(self):
        self.snapshot()
        self.decide()
        timing = self.root / 'timing.json'
        write_json(timing, {'status': 'pending', 'run_id': 'other', 'run_attempt': '1'})
        args = ['delivery', 'confirm', '--site', str(self.site), '--receipt', str(self.receipt), '--timing', str(timing)]
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '123'}), patch('sys.argv', args):
            with self.assertRaises(ValueError): main()
        entry = json.loads((self.site / 'data/reports.json').read_text(encoding='utf-8'))[0]
        write_json(timing, {'status': 'pending', 'run_id': '123', 'run_attempt': '1',
                            'report': report_identity(self.site, entry)})
        (self.site / 'data/report.html').write_text('changed since packaging')
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}), patch('sys.argv', args):
            with self.assertRaises(ValueError): main()
        self.assertFalse(self.receipt.exists())

    def test_workflow_has_three_slots_and_success_only_receipt(self):
        # YAML 用獨立解析器在 CI 外額外檢查；此處保護排程與失敗恢復關鍵設定。
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/daily-report.yml').read_text(encoding='utf-8-sig')
        for minute in ('0', '17', '37'):
            self.assertIn(f"cron: '{minute} 8 * * *'", text)
        self.assertIn("if: steps.deployment.outcome == 'failure'", text)
        self.assertIn("steps.query.outputs.changed == 'true'", text)
        self.assertIn('cancel-in-progress: false', text)

    def test_backup_delay_uses_its_own_slot_and_records_decision(self):
        timing = self.root / 'timing.json'
        args = ['delivery', 'prepare', '--site', str(self.site), '--receipt', str(self.receipt), '--timing', str(timing)]
        env = {'GITHUB_EVENT_NAME': 'schedule', 'TRIGGER_SCHEDULE': '17 8 * * *',
               'RUN_CREATED_AT': '2026-11-11T00:19:00Z', 'RUN_STARTED_AT': '2026-11-11T00:19:01Z'}
        with patch('pmot.delivery.datetime') as dt, patch.dict(os.environ, env), patch('sys.argv', args):
            dt.now.return_value = NOW
            dt.fromisoformat.side_effect = datetime.fromisoformat
            main()
        record = json.loads(timing.read_text(encoding='utf-8'))
        self.assertEqual(record['trigger_delay_seconds'], 120)
        self.assertEqual(record['decision'], 'generate')
        self.assertEqual(record['workflow_started_at'], env['RUN_STARTED_AT'])

    def test_prepare_failure_keeps_timing_evidence(self):
        timing = self.root / 'timing.json'
        args = ['delivery', 'prepare', '--site', str(self.site), '--receipt', str(self.receipt), '--timing', str(timing)]
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch'}), patch('sys.argv', args), patch('pmot.delivery.trading_day', side_effect=ValueError('official unavailable')):
            with self.assertRaises(ValueError): main()
        record = json.loads(timing.read_text(encoding='utf-8'))
        self.assertEqual(record['decision'], 'failed')
        self.assertIn('prepared_at', record)
