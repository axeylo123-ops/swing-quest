from datetime import date

import pytest

from swingquest.sec import feed
from swingquest.sec.client import RateLimiter, SecClient


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_rate_limiter_spaces_requests():
    clock = FakeClock()
    rl = RateLimiter(5, clock=clock, sleep=clock.sleep)
    for _ in range(11):
        rl.wait()
    assert clock.t == pytest.approx(10 / 5)  # 11 calls at 5/sec = 2 seconds


def test_client_refuses_more_than_10_per_second():
    with pytest.raises(ValueError):
        SecClient(user_agent="Test test@example.com", max_per_second=20)


class FakeResp:
    def __init__(self, status, text="ok"):
        self.status_code, self.text = status, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, statuses):
        self.headers, self.statuses, self.calls = {}, list(statuses), 0

    def get(self, url, timeout):
        self.calls += 1
        return FakeResp(self.statuses.pop(0))


def test_client_backs_off_on_429_and_sends_user_agent():
    sleeps = []
    session = FakeSession([429, 200])
    c = SecClient(user_agent="Test test@example.com", max_per_second=5,
                  session=session, sleep=sleeps.append)
    assert c.get_text("https://www.sec.gov/x") == "ok"
    assert session.calls == 2
    assert session.headers["User-Agent"] == "Test test@example.com"
    assert max(sleeps) >= 5  # waited before retrying


ATOM = """<feed>
<entry><title>4 - Smith (0001) (Reporting)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1569789/000156978926000017/0001569789-26-000017-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-10-15 &lt;b&gt;AccNo:&lt;/b&gt; 0001569789-26-000017</summary>
<updated>2026-10-15T19:06:51-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="4"/>
<id>urn:tag:sec.gov,2008:accession-number=0001569789-26-000017</id></entry>
<entry><title>4/A - Amended (0002) (Reporting)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2/000000000226000001/x-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-10-15</summary>
<updated>2026-10-15T18:00:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="4/A"/>
<id>urn:tag:sec.gov,2008:accession-number=0000000002-26-000001</id></entry>
</feed>"""


def test_parse_feed_keeps_form4_only():
    refs = feed.parse_feed(ATOM)
    assert len(refs) == 1
    r = refs[0]
    assert r.accession == "0001569789-26-000017"
    assert r.filed_date == "2026-10-15"
    assert r.txt_url == "https://www.sec.gov/Archives/edgar/data/1569789/0001569789-26-000017.txt"


IDX = """Form Type   Company Name      CIK   Date Filed  File Name
----------------------------------------------------------------
1-A POS          Energea Portfolio 2 LP     1811470     20250715    edgar/data/1811470/0001811470-25-000023.txt
4                ABSHER JODY K              1815401     20261014    edgar/data/1815401/0001815401-26-000004.txt
4                AFLAC INC                  4977        20261014    edgar/data/4977/0001104659-26-115763.txt
4/A              SOMEONE                    5555        20261014    edgar/data/5555/0000005555-26-000001.txt
"""


def test_parse_daily_index():
    refs = feed.parse_daily_index(IDX)
    assert [r.accession for r in refs] == ["0001815401-26-000004", "0001104659-26-115763"]
    assert refs[0].filed_date == "2026-10-14"


def test_daily_index_url_uses_quarter():
    assert feed.daily_index_url(date(2026, 10, 14)).endswith("/2026/QTR4/form.20261014.idx")
