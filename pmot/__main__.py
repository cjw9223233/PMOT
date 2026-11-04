"""CI entry point: collect only on a verified TWSE normal trading day."""
from datetime import datetime
from pathlib import Path
import argparse
import json
import os
import sys

from .http import Fetcher, parallel
from .sources import TAIPEI, trading_day, yahoo_close, dxy, treasury, tx, spot
from .render import publish, build_index

ROOT = Path(__file__).resolve().parents[1]


def github_output(changed):
    if path := os.environ.get('GITHUB_OUTPUT'):
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(f'changed={str(changed).lower()}\n')


def update(site, now=None, fetch=None):
    now = now or datetime.now(TAIPEI)
    fetch = fetch or Fetcher(now)
    gate = trading_day(fetch, now)
    if not gate['open']:
        github_output(False)
        print('SKIP: ' + gate['reason'])
        return False
    tasks = {
        'sp500': lambda: yahoo_close(fetch, '^GSPC', now, True),
        'nasdaq': lambda: yahoo_close(fetch, '^IXIC', now, True),
        'dow': lambda: yahoo_close(fetch, '^DJI', now, True),
        'tsm': lambda: yahoo_close(fetch, 'TSM', now),
        'sox': lambda: yahoo_close(fetch, '^SOX', now, True),
        'tx': lambda: tx(fetch, now), 'spot': lambda: spot(fetch, now),
        'treasury': lambda: treasury(fetch, now), 'dxy': lambda: dxy(fetch, now)}
    quotes = parallel(tasks)
    defaults = {
        'sp500': ['https://finance.yahoo.com/quote/%5EGSPC/'], 'nasdaq': ['https://finance.yahoo.com/quote/%5EIXIC/'],
        'dow': ['https://finance.yahoo.com/quote/%5EDJI/'], 'tsm': ['https://finance.yahoo.com/quote/TSM/'],
        'sox': ['https://finance.yahoo.com/quote/%5ESOX/'], 'tx': ['https://www.taifex.com.tw/cht/3/futDailyMarketReport', 'https://www.tradingview.com/symbols/TAIFEX-TX1!/'],
        'spot': ['https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK'],
        'treasury': ['https://home.treasury.gov/resource-center/data-chart-center/interest-rates', 'https://finance.yahoo.com/quote/%5ETNX/'],
        'dxy': ['https://finance.yahoo.com/quote/DX-Y.NYB/', 'https://www.tradingview.com/symbols/TVC-DXY/']}
    for key, value in quotes.items():
        value.setdefault('sources', defaults[key])
    if not any(v.get('ok') for k, v in quotes.items() if k != 'spot'):
        raise ValueError('All market sources failed; retaining previous published report')
    cutoff = datetime.now(TAIPEI)
    data = {'schema_version': 1, 'date': now.date().isoformat(), 'scheduled_time': '08:30 Asia/Taipei', 'cutoff': cutoff.isoformat(timespec='seconds'), 'generated_at': datetime.now(TAIPEI).isoformat(timespec='seconds'), 'gate': gate, 'quotes': quotes, 'source_audit': fetch.audit}
    publish(data, site)
    github_output(True)
    confirmed = sum(bool(v.get('ok')) for v in quotes.values())
    print(f'PUBLISHED: {data["date"]}; confirmed {confirmed}/{len(quotes)} sources')
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f'### PMOT {data["date"]}\n\nVerified sources: {confirmed}/{len(quotes)}.\n\nActual cutoff: {data["cutoff"]}\n')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['update', 'build'])
    parser.add_argument('--site', type=Path, default=ROOT / 'site')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            build_index(args.site)
            github_output(True)
        else:
            update(args.site)
    except Exception as exc:
        github_output(False)
        print('FAILED (previous report retained): ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
