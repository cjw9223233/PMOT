"""Bounded public HTTPS requests. Never disable TLS verification."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import time
from urllib.request import Request, urlopen


class Fetcher:
    def __init__(self, now, timeout=20):
        self.now = now
        self.timeout = timeout
        self.audit = []

    def text(self, url):
        if not url.startswith('https://'):
            raise ValueError('Only HTTPS public sources are accepted')
        last = None
        for attempt in range(2):
            try:
                request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PMOT/1.0)', 'Accept': '*/*'})
                with urlopen(request, timeout=self.timeout) as response:
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
        return json.loads(self.text(url))


def parallel(tasks):
    """Independent source calls; retain each failure rather than filling values."""
    def run(item):
        key, fn = item
        try:
            return key, fn()
        except Exception as exc:
            return key, {'ok': False, 'error': str(exc), 'value': None}
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        return dict(pool.map(run, tasks.items()))
