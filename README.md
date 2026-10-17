# Swing Quest

A swing-trading signal system that looks for stocks where company insiders
(CEOs, CFOs, directors) are buying shares with their own money, scores each
setup, and honestly tracks whether the picks work.

> Status: under construction (Phase 2: signals done). Full guide coming in Phase 7.

## What works so far

```bash
.venv\Scripts\python -m swingquest fetch                     # new insider buys from the SEC live feed
.venv\Scripts\python -m swingquest fetch --date 2026-10-14   # every Form 4 from one day
.venv\Scripts\python -m swingquest prices AAPL MSFT          # price + universe check
.venv\Scripts\python -m swingquest scan                      # fetch + score -> docs/data/today.json
```

### How a stock becomes a pick
1. **Trigger:** an insider files a new open-market purchase (last 5 days).
2. **Universe:** not OTC, not a fund, price > $5, > $10M traded per day.
3. **Score 0-100** from insider facts only (weights in `config/weights.yaml`,
   which only you change): cluster of buyers 25, role 20, $ size 15,
   stake increase 15, first buy in 12 months 10, near 52-week low 15.
4. **Timing label** from the chart (not part of the score):
   *Ready* (back above 20-day average), *Wait* (still falling),
   *Extended* (ran up too fast, don't chase).
5. **Pick** = score >= 60 **and** Ready. Score >= 60 but not Ready = watchlist.
   Nothing qualifies = "No setups today."
6. **Trade plan:** entry zone, stop 2 x ATR below, target set so that even
   buying at the top of the zone gives at least 2:1 reward-to-risk,
   exit after 15 trading days regardless.

- **SEC client** (`swingquest/sec/client.py`): sends your name/email as the
  User-Agent, stays at 5 requests/sec (SEC limit is 10), backs off if asked.
- **Finding filings** (`sec/feed.py`): the live "latest filings" feed for daily
  scans; the nightly daily index (~10 pm ET) to fill gaps.
- **Reading Form 4s** (`sec/form4.py`): keeps only open-market purchases
  (code P) of common stock; works out total $, avg price, the buyer's role,
  and how much the buy grew their existing stake.
- **Saved data**: `data/insider_buys/YYYY-MM.json`, one record per filing.
- **Prices** (`prices/`): a swappable "plug"; yfinance today.
- **Universe** (`universe.py`): not OTC, price > $5, > $10M traded per day.

## Quick start (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # then put your name + email in .env
.venv\Scripts\python -m pytest
```

**Not financial advice.** This is an educational project.
