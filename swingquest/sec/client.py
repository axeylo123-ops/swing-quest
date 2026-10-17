"""A polite HTTP client for SEC EDGAR.

SEC fair-access rules: identify yourself with a User-Agent (name + email)
and never exceed 10 requests per second. We default to 5/sec and back off
when the SEC answers "429 Too Many Requests" or has a temporary error.
"""
import time

import requests

from swingquest import config

RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimiter:
    """Makes sure calls are spaced at least 1/rate seconds apart."""

    def __init__(self, max_per_second: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = 1.0 / max_per_second
        self.clock = clock
        self.sleep = sleep
        self._last = None

    def wait(self):
        now = self.clock()
        if self._last is not None:
            gap = self.min_interval - (now - self._last)
            if gap > 0:
                self.sleep(gap)
                now = self.clock()
        self._last = now


class SecClient:
    def __init__(self, user_agent: str | None = None, max_per_second: float | None = None,
                 session: requests.Session | None = None, sleep=time.sleep):
        rate = max_per_second or config.settings()["sec"]["max_requests_per_second"]
        if rate > 10:
            raise ValueError("SEC fair-access limit is 10 requests/second")
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or config.sec_user_agent(),
            "Accept-Encoding": "gzip, deflate",
        })
        self.limiter = RateLimiter(rate, sleep=sleep)
        self.sleep = sleep
        self.request_count = 0

    def get(self, url: str, retries: int = 4) -> requests.Response:
        for attempt in range(retries + 1):
            self.limiter.wait()
            self.request_count += 1
            try:
                resp = self.session.get(url, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == retries:
                    raise
                # internet blips (Wi-Fi drop, DNS hiccup): wait 5, 10, 20, 40 s
                self.sleep(5 * 2 ** attempt)
                continue
            if resp.status_code in RETRY_STATUSES and attempt < retries:
                # 429 means "slow down": wait longer each time (1, 2, 4, 8 s...)
                self.sleep(2 ** attempt * (5 if resp.status_code == 429 else 1))
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    def get_text(self, url: str) -> str:
        return self.get(url).text

    def get_json(self, url: str):
        return self.get(url).json()
