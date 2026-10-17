# Swing Quest

Swing Quest finds US stocks where company insiders (CEOs, CFOs, directors, big
investors) just bought shares **with their own money**. It turns the best of them
into "quests": a buy zone, a stop-loss, a target, and a 15-trading-day time
limit. Then it **honestly tracks whether they work**, and shows everything in a
game-styled dashboard you can check in 10–15 minutes after work.

> **Not financial advice.** An educational project. Every trade decision is yours.

---

## How to use it (your 10–15 minutes)

| When | Where | What to do |
|---|---|---|
| Every weekday evening | **Quest Board** | An empty board is normal: patience earns XP too. If quests are posted, read each scroll. |
| When a quest appears | Quest scroll | **Enter at:** buy only inside this price range at the next open, and skip it if the price opens higher. **Retreat:** your stop-loss; place it right after buying. **Treasure:** your target. **Return by:** sell on this date if neither was hit. **How many shares?:** sized so a stop-out costs only your chosen % of the account. |
| After deciding | Quest scroll | **Seal as reviewed** (+5 XP) and **swear the oath** (+15 XP). Passing on a quest on purpose also counts. |
| While holding | **Your Active Quests** | Day count, profit or loss, and distance to the retreat and treasure. Graded automatically. |
| Once a week | **Reckoning** | Flip the six runes to see which parts of the score help. If a change is **Recommended**, you decide whether to apply it (see below). |
| Whenever curious | **Chronicle** | "Can I trust the quests?" in plain words. Use **Ask the Oracle** to see how any kind of past signal did. |
| Optional | **Treasury** | Set your account size and risk per quest. Import your Questrade **Positions** export (Excel or CSV) to see your holdings next to the quests. It's read only in your browser and never uploaded; account numbers are dropped immediately. |

**Changing the rules:** open `config/weights.yaml` (scoring) or
`config/settings.yaml` (universe and trade rules), edit the numbers, save, commit.
The weekly report writes its suggestions to `config/weights_proposed.yaml`, but
**nothing changes unless you edit `weights.yaml` yourself.**

---

## How it works, in plain words

1. **Read insider filings.** Every insider trade must be reported to the SEC on
   a "Form 4". Swing Quest reads them from SEC EDGAR, politely: it sends your
   name/email as required and stays at 5 requests a second (the limit is 10).
2. **Keep only real purchases.** Code "P" (open-market buys) of common stock.
   Option exercises, grants, gifts and sales are ignored. Pre-scheduled 10b5-1
   plan buys are ignored too.
3. **Universe:** not OTC, not a fund, price above $2 (optional ceiling), and
   more than $10M traded per day so you can get in and out.
4. **Score 0–100** from six insider facts: several insiders buying (cluster),
   the buyer's rank, dollars spent, how much it grew their stake, first buy in
   12 months, and nearness to the 52-week low.
5. **Timing ("the path")** from the chart: *Open* (back above the 20-day
   average), *Blocked* (still falling), *Don't chase* (ran up too fast).
6. **A quest** = score at or above the minimum **and** an open path. Good score
   but blocked = a *Rumor* (watch only).
7. **Trade plan:** stop = 2 × ATR (the stock's typical daily move) below the
   price; target set so reward is at least 2× risk even at the top of the buy
   zone; exit after 15 trading days regardless.

### Honest testing
- **Backtest:** every past insider buy since late 2023 is replayed with the same
  code, using only what was known at the time. Entry is at the next day's open;
  the trade is skipped if it opens above the zone; if the stop and target are
  hit the same day, the stop counts first; a gap through the stop exits at the
  worse open.
- **Live tracking:** every signal the daily scan scores is logged once and graded
  automatically with the same rules (`data/signals/live.json`).
- **Scorecard:** results by score, buyer, timing, price and period, vs SPY.
  Groups under 30 signals are marked "not enough data".
- **Weekly report:** judges each factor, proposes small changes tuned to your
  goal of about 4 quests a month, and replays them on the older and newer half
  of history. A change is recommended only if the *weaker* half improves.

### What the data says so far (Nov 2023 – Sep 2026)
Your current rules (option B: score 65+, price $2–$30), replayed on 13,440
insider-buying events:
- **97 finished quests, about 2.8 a month. 56% won, average trade +5.0%,
  +3.9% vs the market** over the same 15 days.
- But the halves differ a lot: older half +1.1% vs the market, newer half
  +6.7%. Recent months were unusually good for small stocks. Expect something
  closer to the older half, and let the live record decide.
- Higher scores don't keep getting better (80+ did worse than 60–79), so the
  weekly report keeps re-checking the weights.
- Insider buying matters more at cheaper, smaller companies. Big-investor and
  CEO/CFO buys beat director buys. Most quests end at the 15-day limit.

---

## Commands (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env                      # put your name + email in .env
.venv\Scripts\python -m pytest              # 100 tests
.venv\Scripts\python -m swingquest daily    # fetch + scan + log + grade (what automation runs)
.venv\Scripts\python -m swingquest health   # weekly report + suggestions (never applied)
.venv\Scripts\python -m swingquest backtest # replay history -> scorecard (~10 min)
.venv\Scripts\python -m swingquest backfill --days 2026-04-01:2026-10-13 --rate 8   # resumable
```

Dashboard locally: `.venv\Scripts\python -m http.server 8765 --directory docs`,
then open http://localhost:8765.

## Folder map
```
config/          weights.yaml (yours), weights_proposed.yaml (suggestions), settings.yaml
swingquest/      sec/ (SEC client, Form 4 reader, bulk + daily backfill), prices/ (swappable
                 price source), signals/ (score, timing, plan, scan), backtest/ (engine,
                 outcomes, scorecard), tracker.py (live log), health.py (weekly report)
data/            insider purchases, backtest rows, live signal log, fetch state
docs/            the dashboard (GitHub Pages) + docs/data/*.json it reads
.github/         daily scan, weekly health, tests
tests/           100 tests for parsing, scoring, backtest math, tracking, health
```

## Privacy
- Your SEC name/email live in `.env` (git-ignored) or a GitHub secret.
- `*.csv` is git-ignored. Portfolio files are read only in your browser
  (localStorage), account columns are dropped first, and nothing is uploaded.
- Game progress and your trading rules are stored only in your browser.

---

## Known weaknesses
1. **Survivorship bias.** Free prices (yfinance) lack many delisted companies.
   About 3,400 past events had no prices, so results are likely somewhat better
   than reality, especially for cheap stocks.
2. **The edge is small.** Even the best settings beat the market by roughly
   1–2.5% per 3-week trade on average, with many losing trades. Live results are
   just starting; until about 30 quests finish, trust the backtest only partly.
3. **Tuned on the same history it's judged on.** The both-halves check reduces,
   but doesn't remove, the risk of fitting luck.
4. **US only.** Canadian insiders report to SEDI, which has no free feed.
   Canadian holdings show "no signal coverage".
5. **yfinance is unofficial.** It can break or throttle. The downloader retries
   and waits, but a bad day can mean a missed scan.
6. **No earnings-date check.** A quest can run straight into an earnings report,
   which can cause a big overnight jump either way.
7. **Prices are split-adjusted**, so a few old trades fail the price sanity check
   and are skipped (about 700 events, mostly ticker changes).
8. **Exits are simple:** a fixed 2 × ATR stop, a 2:1 target and 15 days. Most
   quests time out; a closer stop wasn't clearly better in testing.

## Next upgrades
1. **A paid price source with delisted stocks** (e.g. EODHD or Polygon, about
   US$20–30/month) to remove survivorship bias. The price "plug" makes this a
   one-file change. *(Costs money: your call.)*
2. **Earnings-date warning** on each quest.
3. **Trade journal from Questrade activity exports**: check automatically
   whether real trades kept the oath.
4. **Canadian coverage (SEDI)** if a usable data source appears.
5. **Smarter exits to test:** trailing stops, or holding winners past 15 days.
6. **New quests:** e.g. "follow 10 quests without breaking a vow". Badges are
   one list in `docs/js/game.js`.
