"""命令與 CI 入口：先確認交易日，再組合資料與發布。

閱讀路線：main() 解析 build／update → update() 查核 → render.publish() 寫檔。
build 只讀既有報告；update 才連網。詳細資料契約見 docs/DATA_GUIDE.md。
"""
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
    """把是否有可部署內容寫入 GitHub Actions 的步驟輸出。

    changed 是布林值；工作流程用 changed=true 決定是否提交、封裝及部署。
    本機沒有 GITHUB_OUTPUT 環境變數時不寫任何檔案。
    """
    if path := os.environ.get('GITHUB_OUTPUT'):
        with open(path, 'a', encoding='utf-8') as stream:
            stream.write(f'changed={str(changed).lower()}\n')


def update(site, now=None, fetch=None):
    """完成一次當日更新；成功發布回傳 True，確認休市回傳 False。

    site 是輸出目錄；now 是含時區時間，fetch 是下載器，兩者可注入以利測試。
    交易日不明或主要行情全失敗時拋出例外；部分行情失敗則保留缺漏。
    所有來源查核發生在 publish 前；publish 自身尚不是整批原子寫檔。
    """
    now = now or datetime.now(TAIPEI)
    fetch = fetch or Fetcher(now)
    # 交易日是整次工作的前置條件，不能等到寫報告時才補查。
    gate = trading_day(fetch, now)
    if not gate['open']:
        github_output(False)
        print('SKIP: ' + gate['reason'])
        return False
    # lambda 延後呼叫；字典建立時不連網，由 parallel() 分配執行緒。
    tasks = {
        'sp500': lambda: yahoo_close(fetch, '^GSPC', now, True),
        'nasdaq': lambda: yahoo_close(fetch, '^IXIC', now, True),
        'dow': lambda: yahoo_close(fetch, '^DJI', now, True),
        'tsm': lambda: yahoo_close(fetch, 'TSM', now),
        'sox': lambda: yahoo_close(fetch, '^SOX', now, True),
        'tx': lambda: tx(fetch, now), 'spot': lambda: spot(fetch, now),
        'treasury': lambda: treasury(fetch, now), 'dxy': lambda: dxy(fetch, now)}
    quotes = parallel(tasks)
    # 即使來源失敗，仍留下可點擊查詢網址；補的是網址，不是報價。
    defaults = {
        'sp500': ['https://finance.yahoo.com/quote/%5EGSPC/'], 'nasdaq': ['https://finance.yahoo.com/quote/%5EIXIC/'],
        'dow': ['https://finance.yahoo.com/quote/%5EDJI/'], 'tsm': ['https://finance.yahoo.com/quote/TSM/'],
        'sox': ['https://finance.yahoo.com/quote/%5ESOX/'], 'tx': ['https://www.taifex.com.tw/cht/3/futDailyMarketReport', 'https://www.tradingview.com/symbols/TAIFEX-TX1!/'],
        'spot': ['https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK'],
        'treasury': ['https://home.treasury.gov/resource-center/data-chart-center/interest-rates', 'https://finance.yahoo.com/quote/%5ETNX/'],
        'dxy': ['https://finance.yahoo.com/quote/DX-Y.NYB/', 'https://www.tradingview.com/symbols/TVC-DXY/']}
    for key, value in quotes.items():
        value.setdefault('sources', defaults[key])
    # spot 只是夜盤的比較基準，單靠它成功不足以產出市場觀察報告。
    if not any(v.get('ok') for k, v in quotes.items() if k != 'spot'):
        raise ValueError('All market sources failed; retaining previous published report')
    # 時間在查詢後重新讀取，不能把原訂 08:00 寫成實際完成時間。
    cutoff = datetime.now(TAIPEI)
    data = {'schema_version': 1, 'date': now.date().isoformat(), 'scheduled_time': '08:00 Asia/Taipei', 'cutoff': cutoff.isoformat(timespec='seconds'), 'generated_at': datetime.now(TAIPEI).isoformat(timespec='seconds'), 'gate': gate, 'quotes': quotes, 'source_audit': fetch.audit}
    # 檔案寫完才回報 changed=true，避免下載成功就誤觸發部署。
    publish(data, site)
    github_output(True)
    confirmed = sum(bool(v.get('ok')) for v in quotes.values())
    print(f'PUBLISHED: {data["date"]}; confirmed {confirmed}/{len(quotes)} sources')
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f'### PMOT {data["date"]}\n\nVerified sources: {confirmed}/{len(quotes)}.\n\nActual cutoff: {data["cutoff"]}\n')
    return True


def main():
    """解析命令，成功／正常略過回傳 0，例外回傳 1 給 CI 判斷。

    --site 可將練習輸出隔離到 tmp；不提供繞過交易日或猜補數據的選項。
    """
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
