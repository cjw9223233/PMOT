"""交付狀態機：報告存在不等於部署成功；補跑重用快照，成功才留下收據。"""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import os

from .sources import TAIPEI, trading_day
from .http import Fetcher
from .render import build_index

ROOT = Path(__file__).resolve().parents[1]


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def report_identity(site, entry):
    """核對三份快照都存在，以內容雜湊綁定收據，不能只憑日期略過。"""
    digest = hashlib.sha256()
    for name in (entry['content'], entry['path'], str(Path(entry['content']).with_suffix('.json'))):
        path = (site / name).resolve()
        if not path.is_relative_to(site.resolve()):
            raise ValueError('Report path escapes site')
        digest.update(path.read_bytes())
    website = hashlib.sha256()
    for path in sorted([site / 'index.html', site / 'prompt.md', * (site / 'assets').rglob('*')]):
        if path.is_file():
            website.update(path.relative_to(site).as_posix().encode())
            website.update(path.read_bytes())
    return {'date': entry['date'], 'content': entry['content'], 'sha256': digest.hexdigest(),
            'website_sha256': website.hexdigest()}


def prepare(site, receipt_path, now, event, fetch=None, gate_info=None):
    """push 一律重建；每日／手動先查交易日，再判斷新建、重試或略過。"""
    if event != 'push':
        gate = trading_day(fetch or Fetcher(now), now)
        if gate_info is not None:
            gate_info.update(gate)
        if not gate['open']:
            return 'skip', gate['reason']
    entries = read_json(site / 'data/reports.json', [])
    if event == 'push':
        build_index(site)
        return 'deploy', '程式更新：重建既有報告'
    today = [e for e in entries if e['date'] == now.date().isoformat()]
    if not today:
        return 'generate', '今日尚無報告'
    latest = max(today, key=lambda e: e['generated_at'])
    build_index(site)
    identity = report_identity(site, latest)  # 缺檔必須報錯，不能假裝已交付。
    receipt = read_json(receipt_path, {})
    if receipt.get('status') == 'success' and receipt.get('report') == identity:
        return 'skip', '當日報告已成功部署'
    # 發布時清單已按時間排序；重試不查新行情、不新增另一份報告。
    if entries[0] != latest:
        raise ValueError('Latest manifest entry is not today report')
    return 'deploy', '重用今日快照：尚無相符的成功部署收據'


def clock():
    return datetime.now(TAIPEI).isoformat(timespec='seconds')


def timeliness(receipt, day):
    """交付成功與準時是兩件事；不能以 run 綠燈或報告產出時間取代部署確認。"""
    deadline = datetime.fromisoformat(day + 'T09:00:00+08:00')
    result = {'deadline_at': deadline.isoformat(), 'status': 'unconfirmed'}
    if receipt.get('status') != 'success' or receipt.get('report', {}).get('date') != day:
        return result
    try:
        completed = datetime.fromisoformat(receipt['deployment_completed_at'])
        generated = datetime.fromisoformat(receipt['generated_at'])
        if completed.tzinfo is None or generated.tzinfo is None:
            return result
        completed, generated = completed.astimezone(TAIPEI), generated.astimezone(TAIPEI)
        if generated.date().isoformat() != day or completed < generated:
            return result
    except (KeyError, ValueError, TypeError):
        return result
    result.update(status='on_time' if completed < deadline else 'late',
                  deployment_completed_at=completed.isoformat(),
                  late_seconds=max(0, int((completed - deadline).total_seconds())))
    return result


def report_timeliness(receipt, day):
    result = timeliness(receipt, day)
    summary('### 開盤前交付時效\n\n' + json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] != 'on_time':
        # 不把已成功部署改寫成未部署；以獨立欄位及 Actions warning 揭露 SLA 未達。
        print('::warning title=Premarket delivery deadline::09:00 delivery ' + result['status'])
    return result


def output(name, value):
    if path := os.environ.get('GITHUB_OUTPUT'):
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(f'{name}={value}\n')


def summary(value):
    print(value)
    if path := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(value + '\n\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'package', 'confirm', 'checkpoint'])
    parser.add_argument('--site', type=Path, default=ROOT / 'site')
    parser.add_argument('--receipt', type=Path, default=ROOT / '.pmot/deployment.json')
    parser.add_argument('--timing', type=Path, default=ROOT / 'delivery-timing.json')
    parser.add_argument('--check', type=Path, default=ROOT / '.pmot/check.json')
    args = parser.parse_args()
    if args.command == 'prepare':
        now = datetime.now(TAIPEI)
        started = clock()
        scheduled = now.replace(hour=8, minute=0, second=0, microsecond=0)
        timing = {'event': os.environ.get('GITHUB_EVENT_NAME', 'local'),
                  'schedule': os.environ.get('TRIGGER_SCHEDULE', ''),
                  'target_at': scheduled.isoformat(), 'workflow_started_at': os.environ.get('RUN_STARTED_AT') or started,
                  'run_created_at': os.environ.get('RUN_CREATED_AT') or None,
                  'date': now.date().isoformat(), 'market_state': 'unknown',
                  'trigger_source': os.environ.get('TRIGGER_SOURCE') or os.environ.get('GITHUB_EVENT_NAME', 'local'),
                  'external_requested_at': os.environ.get('EXTERNAL_REQUESTED_AT') or None,
                  'prepared_at': started, 'decision': 'checking',
                  'run_url': os.environ.get('RUN_URL', ''), 'run_id': os.environ.get('GITHUB_RUN_ID', ''),
                  'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '1')}
        if timing['event'] == 'schedule' and timing['run_created_at']:
            # 補跑相對自己的時槽計算；不把 08:17 的正常喚醒誤稱晚了 17 分鐘。
            minute = int((timing['schedule'] or '0').split()[0])
            slot = scheduled.replace(minute=minute)
            timing['trigger_expected_at'] = slot.isoformat()
            timing['trigger_delay_seconds'] = max(0, int((datetime.fromisoformat(timing['run_created_at'].replace('Z', '+00:00')) - slot).total_seconds()))
        write_json(args.timing, timing)
        gate_info = {}
        try:
            action, reason = prepare(args.site, args.receipt, now, os.environ.get('GITHUB_EVENT_NAME', 'workflow_dispatch'), gate_info=gate_info)
        except Exception as exc:
            timing.update(decision='failed', reason=str(exc))
            write_json(args.timing, timing)
            summary('交付查核失敗：' + str(exc))
            raise
        state = 'open' if gate_info.get('open') is True else 'closed' if gate_info.get('open') is False else 'not_checked'
        timing.update(decision=action, reason=reason, market_state=state)
        write_json(args.timing, timing)
        output('action', action)
        summary('### 交付決策：' + action + '\n\n' + reason + '\n\n```json\n' + json.dumps(timing, ensure_ascii=False, indent=2) + '\n```')
        if action == 'skip' and reason == '當日報告已成功部署':
            report_timeliness(read_json(args.receipt, {}), now.date().isoformat())
    elif args.command == 'checkpoint':
        timing = read_json(args.timing)
        if not timing:
            raise ValueError('No check evidence to save')
        # 程式改版 push 不查交易日，不能蓋掉當日官方休市／開市查核證據。
        if timing.get('event') != 'push':
            write_json(args.check, timing)
    elif args.command == 'package':
        entry = read_json(args.site / 'data/reports.json')[0]
        timing = read_json(args.timing)
        timing.update(report=report_identity(args.site, entry), generated_at=entry['generated_at'],
                      deployment_requested_at=clock(), status='pending')
        write_json(args.site / 'data/delivery.json', timing)
        write_json(args.timing, timing)
        summary('部署送出時間：' + timing['deployment_requested_at'])
    else:
        # 只允許部署 action 成功後執行；收據提交失敗只會多做一次安全重試。
        timing = read_json(args.timing)
        if timing.get('status') != 'pending':
            raise ValueError('No pending deployment to confirm')
        if timing.get('run_id') != os.environ.get('GITHUB_RUN_ID', '') or timing.get('run_attempt') != os.environ.get('GITHUB_RUN_ATTEMPT', '1'):
            raise ValueError('Deployment receipt does not belong to this run attempt')
        entry = read_json(args.site / 'data/reports.json')[0]
        if report_identity(args.site, entry) != timing['report']:
            raise ValueError('Report changed since packaging; refusing success receipt')
        timing.update(status='success', deployment_completed_at=clock())
        timing['timeliness'] = report_timeliness(timing, timing['report']['date'])
        write_json(args.receipt, timing)
        summary('### 部署成功\n\n確認時間：' + timing['deployment_completed_at'] + '\n\n' + timing['run_url'])


if __name__ == '__main__':
    main()
