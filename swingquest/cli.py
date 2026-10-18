"""Command line entry point.

    python -m swingquest fetch                 # new filings from the live feed
    python -m swingquest fetch --date 2026-10-14   # one full day (nightly index)
    python -m swingquest prices AAPL MSFT      # quick price + universe check
    python -m swingquest scan                  # fetch + score -> docs/data/today.json
    python -m swingquest daily                 # fetch + scan + log + grade (what automation runs)
    python -m swingquest health                # weekly report + suggested weights (never applied)
    python -m swingquest backfill --bulk 2022q4:2026q1     # past purchases (bulk files)
    python -m swingquest backfill --days 2026-04-01:2026-10-13   # gap-fill by day
    python -m swingquest backtest              # replay history -> docs/data/scorecard.json
"""
import argparse
from datetime import date, timedelta


def cmd_fetch(args):
    from swingquest.sec.client import SecClient
    from swingquest.sec.fetch import fetch_day, fetch_latest
    client = SecClient()
    if args.date:
        result = fetch_day(client, date.fromisoformat(args.date))
    else:
        result = fetch_latest(client)
    print(f"Done: {result} ({client.request_count} SEC requests)")


def cmd_prices(args):
    from swingquest.prices.base import get_price_source
    from swingquest.universe import exchange_map, is_us_listed, liquidity_check
    end = date.today()
    data = get_price_source().history(args.tickers, end - timedelta(days=60), end)
    exchanges = exchange_map()
    for t in args.tickers:
        if t not in data:
            print(f"{t}: no price data")
            continue
        df = data[t]
        check = liquidity_check(df, df.index[-1])
        status = "IN universe" if check["ok"] and is_us_listed(t, exchanges) else \
            f"OUT ({check.get('reason', 'not US-listed')})"
        print(f"{t}: last close {df['close'].iloc[-1]:.2f} on {df.index[-1]:%Y-%m-%d} "
              f"| exchange {exchanges.get(t)} | {status}")


def cmd_scan(args):
    from swingquest.signals.scan import run_scan
    if not args.no_fetch:
        cmd_fetch(argparse.Namespace(date=None))
    r = run_scan()
    s = r["summary"]
    print(f"\nScan for {r['as_of']}: {s['insider_buys_in_window']} insider buys in window, "
          f"{s['stocks_with_new_buys']} stocks with new buys, {s['skipped']} skipped.")
    print(f"==> {r['message']}")
    for label, rows in (("PICK", r["picks"]), ("WATCH", r["watchlist"])):
        for p in rows:
            pl = p["plan"]
            print(f"\n[{label}] {p['ticker']} ({p['company']})  score {p['score']}  timing {p['timing']}")
            print(f"  entry {pl['entry_low']}-{pl['entry_high']}  stop {pl['stop']}  target {pl['target']}"
                  f"  ({pl['reward_risk']}:1, exit after {pl['time_stop_days']} days)")
            for reason in p["reasons"]:
                print(f"  + {reason}")
            for note in p["timing_notes"]:
                print(f"  ~ {note}")
            for c in p["cautions"]:
                print(f"  ! {c}")
    print("\nSaved docs/data/today.json")


def cmd_backfill(args):
    from swingquest.sec import bulk
    from swingquest.sec.client import SecClient
    client = SecClient(max_per_second=args.rate)
    if args.bulk:
        first, last = args.bulk.split(":")
        print(bulk.backfill_bulk(client, first, last))
    if args.days:
        first, last = args.days.split(":")
        print(bulk.backfill_days(client, date.fromisoformat(first), date.fromisoformat(last)))
    print(f"({client.request_count} SEC requests)")


def cmd_backtest(args):
    from swingquest.backtest import report
    if args.earnings:   # mark which past quests/rumors had earnings inside their window
        import json
        from swingquest import events
        rows = json.loads(report.ROWS_FILE.read_text(encoding="utf-8"))
        meta = json.loads(report.META_FILE.read_text(encoding="utf-8"))
        card = report.save_backtest(events.annotate(rows), meta)
    elif args.rebuild:
        card = report.write_scorecard()
    else:
        from swingquest import store
        from swingquest.backtest.engine import run_backtest
        from swingquest.prices.yfinance_source import YFinanceSource
        from swingquest.sec.client import SecClient
        from swingquest.universe import IssuerProfiles
        state = store.load_state()
        # start once a full year of history exists, so "first buy in 12 months" is always known
        start = args.start or (date.fromisoformat(state["history_start"]) + timedelta(days=400)).isoformat()
        end = args.end or date.today().isoformat()
        profiles = IssuerProfiles(SecClient(max_per_second=args.sec_rate))
        result = run_backtest(start, end, source=YFinanceSource(progress=print), profiles=profiles)
        rows = result.pop("rows")
        card = report.save_backtest(rows, result)
    p = card["backtest"]["picks"]
    print(f"\nPicks: {p['n']} finished, win rate {p['win_rate']}, avg trade {p['avg_trade_return']}, "
          f"avg 15-day vs SPY {p['avg_excess_15']}")
    for b, s in card["backtest"]["by_score_bucket"].items():
        print(f"  score {b:>6}: n={s['n']:>5}  beat SPY {s['beat_spy_rate']}  avg excess 15d {s['avg_excess_15']}"
              f"  {s['label'] or ''}")
    print("Saved docs/data/scorecard.json and data/backtest/rows.json")


def cmd_daily(args):
    """The evening/morning job: fetch -> scan -> log -> grade -> scorecard."""
    from swingquest import tracker
    from swingquest.backtest import report
    from swingquest.signals.scan import run_scan
    if not args.no_fetch:
        cmd_fetch(argparse.Namespace(date=None))
    result = run_scan()
    rows, added = tracker.log_signals(result["evaluated"], result["as_of"])
    rows = tracker.update_outcomes(rows)
    tracker.save_log(rows)
    view = tracker.write_dashboard(rows)
    report.write_scorecard(live_rows=rows)
    print(f"Scan {result['as_of']}: {result['message']} | {added} new signals logged | "
          f"{len(view['open'])} open quests | {len(rows)} signals tracked in total")
    from swingquest import briefs   # on your PC only: the private holdings list never reaches GitHub
    if briefs.load_holdings():
        briefs.write_briefs(briefs.build_briefs(briefs.load_holdings()))
        print("Refreshed your private holding briefs.")


def cmd_briefs(args):
    """Briefs on your holdings. Symbols are remembered privately (git-ignored)."""
    from swingquest import briefs
    symbols = [s.upper() for s in args.symbols] or briefs.load_holdings()
    if not symbols:
        print("Give your symbols, e.g.:  python -m swingquest briefs AAPL SHOP.TO  "
              "(the Treasury's 'Copy command' button builds this for you)")
        return
    briefs.save_holdings(symbols)
    result = briefs.build_briefs(symbols)
    briefs.write_briefs(result)
    for sym, b in result["briefs"].items():
        print(f"\n{sym}: {b['text']}")
    print(f"\nSaved privately to {briefs.BRIEFS_FILE} (git-ignored). Refresh the Treasury to see them.")


def cmd_health(args):
    from swingquest import health
    r = health.run()
    print(f"System Health for week of {r['week']}:")
    for f in r["factors"]:
        edge = "  n/a " if f["edge"] is None else f"{f['edge'] * 100:+5.1f}%"
        print(f"  {f['label']:22} {edge}  {f['verdict']}")
    print("Suggestions:" if r["suggestions"] else "No changes suggested.")
    for s in r["suggestions"]:
        print(f"  {s['label']}: {s['current']} -> {s['suggested']}  ({s['why']})")
    w = r["whatif"]
    for name in ("current", "proposed"):
        print(f"  {name:9} quests: " + " | ".join(
            f"{h} n={w[name][h]['n']} vsSPY={(w[name][h]['avg_excess_15'] or 0) * 100:+.1f}%" for h in ("all", "older", "newer")))
    print("Recommended: " + ("YES" if r["recommended"] else "no") + "  -> see config/weights_proposed.yaml")


def main(argv=None):
    import sys
    sys.stdout.reconfigure(line_buffering=True)  # show progress lines immediately, even in logs
    p = argparse.ArgumentParser(prog="swingquest")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download new insider purchases from the SEC")
    f.add_argument("--date", help="read one full day from the nightly index (YYYY-MM-DD)")
    f.set_defaults(func=cmd_fetch)
    pr = sub.add_parser("prices", help="check prices and universe rules for tickers")
    pr.add_argument("tickers", nargs="+", type=str.upper)
    pr.set_defaults(func=cmd_prices)
    sc = sub.add_parser("scan", help="fetch new filings, score setups, write today.json")
    sc.add_argument("--no-fetch", action="store_true", help="skip downloading new filings")
    sc.set_defaults(func=cmd_scan)
    bf = sub.add_parser("backfill", help="load past insider purchases")
    bf.add_argument("--bulk", help="quarters from the SEC bulk datasets, e.g. 2022q4:2026q1")
    bf.add_argument("--days", help="day range from nightly indexes, e.g. 2026-04-01:2026-10-13")
    bf.add_argument("--rate", type=float, default=None, help="SEC requests/sec (max 10)")
    bf.set_defaults(func=cmd_backfill)
    dl = sub.add_parser("daily", help="fetch, scan, log and grade signals, update the dashboard")
    dl.add_argument("--no-fetch", action="store_true", help="skip downloading new filings")
    dl.set_defaults(func=cmd_daily)
    br = sub.add_parser("briefs", help="analyst + trend briefs on your holdings (private, git-ignored)")
    br.add_argument("symbols", nargs="*", help="your symbols, e.g. AAPL SHOP.TO (remembered for next time)")
    br.set_defaults(func=cmd_briefs)
    hl = sub.add_parser("health", help="weekly System Health report -> health.json + weights_proposed.yaml")
    hl.set_defaults(func=cmd_health)
    bt = sub.add_parser("backtest", help="replay the scanner through history -> scorecard.json")
    bt.add_argument("--start", help="first signal date (default: 400 days after history starts)")
    bt.add_argument("--end", help="last signal date (default: today)")
    bt.add_argument("--earnings", action="store_true",
                    help="look up earnings dates for past quests/rumors and mark them (uses Yahoo)")
    bt.add_argument("--rebuild", action="store_true",
                    help="rebuild scorecard.json from saved results without re-running")
    bt.add_argument("--sec-rate", type=float, default=None,
                    help="SEC requests/sec for company lookups (lower it if a backfill is running)")
    bt.set_defaults(func=cmd_backtest)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
