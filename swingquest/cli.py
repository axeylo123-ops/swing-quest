"""Command line entry point.

    python -m swingquest fetch                 # new filings from the live feed
    python -m swingquest fetch --date 2026-10-14   # one full day (nightly index)
    python -m swingquest prices AAPL MSFT      # quick price + universe check
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="swingquest")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download new insider purchases from the SEC")
    f.add_argument("--date", help="read one full day from the nightly index (YYYY-MM-DD)")
    f.set_defaults(func=cmd_fetch)
    pr = sub.add_parser("prices", help="check prices and universe rules for tickers")
    pr.add_argument("tickers", nargs="+", type=str.upper)
    pr.set_defaults(func=cmd_prices)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
