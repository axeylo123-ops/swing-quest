# Swing Quest

A stock-picking command center for swing trades (days to a few weeks), built
for a 10-minute check after work. Every weekday it ranks ~1,800 liquid US and
Canadian stocks on six pillars, picks the top ideas with a full trade plan,
and judges the stocks you already own with the same rules.

**Live dashboard:** https://axeylo123-ops.github.io/swing-quest/

> **Not financial advice.** An educational project. Every decision is yours.

---

## Your 10 minutes

| Where | What you get |
|---|---|
| **Command** | What changed since the last trading day, today's **top 3 ideas** (Conviction, upside, buy zone with where the price sits now, stop, target, exit date, pillar meters), the **high-upside lane** (+50% analyst potential, higher risk), the **watchlist**, and a verdict on **each of your holdings** (Add / Hold / Trim? / Review) |
| **Dossier** (tap any stock) | A short analyst note: upside, estimate revisions and earnings beats, genuine insider buying, quality, momentum, value, risks, the trade plan, and how many shares to buy for your risk |
| **Scanner** | Every ranked stock. Sort by any pillar, filter by country, sector or verdict. Press `/` anywhere to search |
| **Holdings** | Import your Questrade file once (Excel or CSV, positions or trade history). It's read **only in your browser**; account numbers are dropped immediately. Set your account size and risk per trade |
| **Record** | How the system's ideas actually did, graded automatically against their own plans |
| **Agents** | A replay of last night's run: 8 pipeline agents (scout, feed, insider analyst, analyst desk, ranker, risk officer, planner, record keeper) doing their step with real counts, plus the review crew's findings and proposals |
| **System** | The pillars, weights and rules in plain words |

## How a stock is judged

Each pillar ranks a stock against all the others (70 = better than 70% of them):

| Pillar | Weight | Measures |
|---|---|---|
| **Upside** | 25 | *Realistic* analyst upside: trusted less with few analysts or wide disagreement, capped at +40% |
| **Analysts** | 15 | Consensus rating, coverage, estimate raises vs cuts per analyst, EPS-estimate trend, earnings-beat record |
| **Insiders** | 15 | *Genuine* open-market buying (company plans, mismatched prices and 10b5-1 plans are filtered out). No buying = neutral |
| **Quality** | 15 | Operating margin, return on equity, debt, growth, free cash flow |
| **Momentum** | 15 | 3-month return vs the market, 6-month return, nearness to the 52-week high, 50/200-day trend |
| **Value** | 10 | Forward P/E and price/sales within its own industry |
| **Risk** | −15 max | Very volatile, small/tiny, heavily indebted, heavily shorted, no analysts, analysts cutting estimates, earnings inside the trade window |
| **Canada** | +3 | A tie-breaker, never the main reason |

A **top idea** ranks high on Conviction (one per sector) **and** has at least 8%
realistic upside, decent quality, limited risk, no estimate cuts, no earnings
report inside the trade window, and a chart whose trend has turned up.
Every idea comes with a plan: buy zone, a stop just under real chart support,
a target at the nearest resistance that pays at least 2× the risk, and a sell
date 15 trading days out regardless.

The **high-upside lane** is separate and riskier: analysts' average target 50%+
above today (3+ analysts), at least two separate catalysts (genuine insider
buying, rising estimates, a big beat, a breakout), a real business, and a
turned-up chart. Wider stop, 30-day limit, size smaller. Names that qualify but
are still falling show as "waiting".

Weights and rules live in `config/weights.yaml` and change only when you edit them.

## Data (all free)

- **SEC EDGAR:** insider filings (Form 4), fetched politely with your name/email.
- **Yahoo Finance (yfinance):** prices daily; analysts, estimates and fundamentals on
  a rolling weekly refresh. The price source is a swappable "plug".
- **Index lists:** S&P 500/400/600 and S&P/TSX Composite members from Wikipedia, weekly.

## Automation

GitHub Actions runs `python -m swingquest daily` on weekdays after the close
(~6:30 pm ET) and before the open (~8 am ET), commits the results, and the
dashboard updates. Your SEC name/email is an encrypted repo secret.

## Commands (Windows, from the project folder)

```bash
.venv\Scripts\python -m swingquest daily          # filings + rank the market + track ideas
.venv\Scripts\python -m swingquest rank --no-fetch # re-rank from cached data
.venv\Scripts\python -m pytest                    # tests
.venv\Scripts\python -m http.server 8765 --directory docs   # dashboard at http://localhost:8765
```

## Honest limits

1. **Analyst and fundamental history isn't free**, so the full system can only be proven
   live (Record tab). The insider pillar was backtested on 2023–2026: about +2% vs the
   market per 15-day trade, but free prices miss some delisted companies, so that's flattering.
2. **Yahoo data is unofficial.** It can be late, missing, or throttled; stale data is kept
   rather than dropped.
3. **Canadian insider trades aren't covered** (SEDI has no free feed). Canadian stocks are
   still ranked on the other five pillars.
4. **Analyst targets are often optimistic**; Upside is a ranking input, not a promise.

## Privacy

- `.env` (your SEC name/email), `*.csv` and `*.xlsx` are git-ignored.
- Holdings, risk rules and XP live only in your browser (localStorage). The public site
  publishes market data only; your holdings are matched against it in your browser.
