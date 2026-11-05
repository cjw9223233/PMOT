"""共用 HTTPS 與平行查詢層，不負責判斷報價是否為正式收盤。

下載成功只是第一關；sources.py 的解析器還會核對日期、時段與單位。
所有網路請求保留預設 TLS 憑證驗證，不用忽略憑證的方式處理連線失敗。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import time
from urllib.request import Request, urlopen


class Fetcher:
    """提供 text／json，並在 audit 留下各來源的下載紀錄。

    audit 的 ok 表示 HTTP 內容讀取成功，不等同於行情解析驗證通過。
    """
    def __init__(self, now, timeout=20):
        """now 提供紀錄用時區；timeout 是每次 HTTP 開啟的逾時秒數。"""
        self.now = now
        self.timeout = timeout
        self.audit = []

    def text(self, url):
        """讀取 HTTPS 文字；最多嘗試兩次，內容超過 12 MB 也會拒收。

        成功紀錄時間與原文 SHA-256；失敗紀錄例外類型並拋出 RuntimeError。
        摘要無法還原原文，目前也沒有整批工作的共同截止時間。
        """
        if not url.startswith('https://'):
            raise ValueError('Only HTTPS public sources are accepted')
        last = None
        # 所有下載錯誤最多重試一次；不是無限重試或指數退避。
        for attempt in range(2):
            try:
                request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PMOT/1.0)', 'Accept': '*/*'})
                with urlopen(request, timeout=self.timeout) as response:
                    # 多讀一個位元組，才能辨認資料是否超過 12 MB 上限。
                    raw = response.read(12_000_001)
                    if len(raw) > 12_000_000:
                        raise ValueError('Source exceeds size limit')
                    charset = response.headers.get_content_charset() or 'utf-8'
                    text = raw.decode(charset)
                self.audit.append({'url': url, 'retrieved_at': datetime.now(self.now.tzinfo).isoformat(), 'status': 'ok', 'sha256': hashlib.sha256(raw).hexdigest()})
                return text
            except Exception as exc:
                last = exc
                if attempt == 0:
                    time.sleep(0.5)
        self.audit.append({'url': url, 'status': 'failed', 'error': type(last).__name__})
        raise RuntimeError(f'{type(last).__name__}: {str(last)[:180]}') from last

    def json(self, url):
        """先套用共用下載保護，再解析 JSON；格式錯誤由呼叫端處理。"""
        return json.loads(self.text(url))


def parallel(tasks):
    """接收 {資料鍵: 無參數函式}，回傳同樣以資料鍵索引的結果。

    最多八個執行緒；各任務失敗轉成 ok=false，不讓單一來源拖垮其他結果。
    tasks 由入口提供且非空；結果用鍵對應，不依下載完成順序配對行情。
    """
    def run(item):
        """把單組來源的例外封裝成缺漏物件，保留原始錯誤供報告揭露。"""
        key, fn = item
        try:
            return key, fn()
        except Exception as exc:
            return key, {'ok': False, 'error': str(exc), 'value': None}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        return dict(pool.map(run, tasks.items()))
