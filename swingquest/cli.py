"""Command line entry point.

    python -m swingquest fetch                 # new filings from the live feed
    python -m swingquest fetch --date 2026-10-14   # one full day (nightly index)
    python -m swingquest prices AAPL MSFT      # quick price + universe check
    python -m swingquest scan                  # fetch + score -> docs/data/today.json
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


def main(argv=None):
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
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
