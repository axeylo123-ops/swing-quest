# Swing Quest

A swing-trading signal system that looks for stocks where company insiders
(CEOs, CFOs, directors) are buying shares with their own money, scores each
setup, and honestly tracks whether the picks work.

> Status: under construction (Phase 3: backtest done). Full guide coming in Phase 7.

## What works so far

```bash
.venv\Scripts\python -m swingquest fetch                     # new insider buys from the SEC live feed
.venv\Scripts\python -m swingquest fetch --date 2026-10-14   # every Form 4 from one day
.venv\Scripts\python -m swingquest prices AAPL MSFT          # price + universe check
.venv\Scripts\python -m swingquest scan                      # fetch + score -> docs/data/today.json
```

### How a stock becomes a pick
1. **Trigger:** an insider files a new open-market purchase (last 5 days).
2. **Universe:** not OTC, not a fund, price > $2, > $10M traded per day.
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
- **Universe** (`universe.py`): not OTC, price > $2, > $10M traded per day.

## Quick start (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # then put your name + email in .env
.venv\Scripts\python -m pytest
```

### The backtest (is this actually working?)

```bash
.venv\Scripts\python -m swingquest backfill --bulk 2022q4:2026q1            # SEC bulk files
.venv\Scripts\python -m swingquest backfill --days 2026-04-01:2026-10-13    # gap, day by day
.venv\Scripts\python -m swingquest backtest                                 # -> docs/data/scorecard.json
```

The backtest replays the live scanner day by day through history, using the
**same** scoring code and only information that was public at the time:

- a signal is judged after the close; we **buy at the next day's open**
- if it opens above the entry zone, the trade is **skipped** (no chasing)
- if stop and target are touched the same day, we assume the **stop** hit first
- a gap through the stop exits at the (worse) opening price
- otherwise exit at the target, the stop, or the close of day 15

The scorecard reports, by score bucket, by factor, by role and by timing:
returns at 5/10/15 days vs SPY, how often signals beat SPY, trade win rate,
average return, and target-first vs stop-first rates. Any group with fewer
than 30 finished signals is marked **"not enough data"**. It also compares the
older and newer half of the period: a big difference suggests luck.

**Known bias:** yfinance has no prices for delisted companies, so failed
companies drop out and results look somewhat better than reality.

**Not financial advice.** This is an educational project.
