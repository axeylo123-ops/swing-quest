"""Runs the brain end to end and writes what the dashboard reads:

docs/data/board.json     top ideas + watchlist (full notes, charts, plans)
docs/data/universe.json  every ranked stock, compact (search, sorting, your holdings)
docs/data/notes.json     analyst-style notes for every ranked stock (loaded on demand)
"""
import json
import math
from datetime import date, datetime, timedelta, timezone

from collections import Counter

from swingquest import brain, crew, events, fundamentals, insider_signal, stocklist, store
from swingquest.config import DATA_OUT_DIR, settings
from swingquest.prices.base import get_price_source
from swingquest.signals.scan import chart_data, market_weather
from swingquest.signals.scoring import load_weights
from swingquest.universe import exchange_map, is_us_listed

INSIDER_DAYS = 60
COMPACT = ["ticker", "name", "country", "sector", "industry", "currency", "price", "mcap", "conviction", "rank",
           "pillars", "penalty", "verdict", "why", "hold", "hold_why", "analyst_upside", "n_analysts", "target",
           "swing_upside", "timing", "rs_3m", "fpe", "flags", "next_earnings"]


def _round(x):
    if isinstance(x, float):
        return round(x, 4) if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_round(v) for v in x]
    return x


def universe_with_insider_names(buys: list[dict]) -> list[dict]:
    """Index members plus any US stock with recent insider buying (not OTC)."""
    stocks = stocklist.load()
    have = {s["ticker"] for s in stocks}
    try:
        exchanges = exchange_map()
    except Exception:
        exchanges = {}
    extra = {}
    for b in buys:
        t = b["ticker"]
        if t not in have and t not in extra and is_us_listed(t, exchanges):
            extra[t] = {"ticker": t, "name": b.get("issuer_name") or t, "sector": None, "index": "Insider buying", "country": "US"}
    return stocks + list(extra.values())


def insider_scores(buys: list[dict], prior: list[dict], price_data: dict, history_start: str | None) -> dict:
    by, prior_by = {}, {}
    for b in buys:
        by.setdefault(b["ticker"], []).append(b)
    for b in prior:
        prior_by.setdefault(b["ticker"], []).append(b)
    return {t: insider_signal.pillar(bs, price_data.get(t), prior_by.get(t, []), history_start) for t, bs in by.items()}


def run(fetch: bool = True, info_budget: int = 350, progress=print) -> dict:
    cfg, trade_cfg = load_weights(), settings()["trade"]
    today = datetime.now(timezone.utc).date()
    buys = store.load_buys((today - timedelta(days=INSIDER_DAYS)).isoformat())
    prior = store.load_buys((today - timedelta(days=INSIDER_DAYS + 400)).isoformat(),
                            (today - timedelta(days=INSIDER_DAYS + 1)).isoformat())
    log = crew.Crew("live" if fetch else "offline")
    stocks = universe_with_insider_names(buys)
    tickers = [s["ticker"] for s in stocks]
    progress(f"Universe: {len(stocks)} stocks")
    n_ca = sum(s.get("country") == "CA" for s in stocks)
    log.done("scout", "Scout", "Reads SEC insider filings and builds the stock list",
             f"{len(buys):,} insider buys in {INSIDER_DAYS} days",
             [f"{len({b['ticker'] for b in buys}):,} companies with insider buying",
              f"{len(stocks):,} stocks to scan ({len(stocks) - n_ca:,} US, {n_ca:,} Canada)"])
    refreshed = 0
    if fetch:
        progress(f"Refreshing fundamentals (up to {info_budget} stalest)...")
        refreshed = fundamentals.refresh_info(tickers, budget=info_budget, progress=progress) or 0
    progress("Loading prices...")
    price_data = get_price_source().history(tickers + ["SPY"], today - timedelta(days=420), today)
    log.done("feed", "Feed", "Downloads prices and company fundamentals",
             f"{len(price_data):,} price histories",
             [f"{refreshed:,} company profiles refreshed" if fetch else "offline run: used cached data",
              f"{len(fundamentals.load()):,} company profiles on file"])
    if price_data.get("SPY") is None or price_data["SPY"].empty:
        raise RuntimeError("No SPY prices (Yahoo down or throttled): not publishing a board built without the market benchmark.")
    hist_start = store.load_state().get("history_start")
    ins = insider_scores(buys, prior, price_data, hist_start)
    genuine = sum(1 for v in ins.values() if v["genuine"])
    excluded = sum(len(v["excluded"]) for v in ins.values())
    best = max(ins.items(), key=lambda kv: kv[1]["score"], default=(None, None))
    log.done("insider", "Insider analyst", "Separates real conviction buys from plans and noise",
             f"{genuine:,} stocks with genuine insider buying",
             [f"{excluded:,} buys thrown out (10b5-1 plans, company plans, odd prices)",
              f"strongest: {best[0]} (insider score {best[1]['score']})" if best[0] else "no genuine buying this period"])

    def build(earn=None):
        return brain.build_board(stocks, fundamentals.load(), price_data, ins, cfg, trade_cfg, earnings_lookup=earn)

    est = 0
    if fetch:   # estimates for the WHOLE universe on a rotation (stalest first), so comparisons are fair
        progress(f"Refreshing earnings estimates (up to {info_budget} stalest)...")
        est = fundamentals.refresh_estimates(tickers, budget=info_budget, progress=progress) or 0
    funds = fundamentals.load()
    rising = sum(1 for f in funds.values() if (f.get("rev_up_30d") or 0) > (f.get("rev_down_30d") or 0))
    log.done("analyst", "Analyst desk", "Tracks analyst targets, estimate changes and earnings beats",
             f"{est:,} estimate sets refreshed" if fetch else "estimates from cache",
             [f"{rising:,} companies where analysts are raising estimates",
              f"{sum(1 for f in funds.values() if f.get('numberOfAnalystOpinions')):,} companies with analyst coverage"])
    board = build(events.earnings_dates if fetch else events.cached_dates)
    board["insiders"] = ins
    crew_report(log, board, cfg)
    write(board, price_data, cfg, len(stocks))
    log.write(board["ranked"][0]["as_of"] if board["ranked"] else None)
    t, h = board["top"], board.get("high", [])
    progress(f"Ranked {len(board['ranked'])} stocks. Top ideas: " + (", ".join(f"{s['ticker']} ({s['conviction']})" for s in t) or "none today")
             + " | High-upside: " + (", ".join(f"{s['ticker']} ({s['potential'] * 100:+.0f}% potential)" for s in h) or "none ready today")
             + " | waiting: " + (", ".join(s["ticker"] for s in board.get("high_wait", [])) or "none"))
    return board


def crew_report(log: "crew.Crew", board: dict, cfg: dict) -> None:
    """What the ranker, risk officer and planner did, in their own words."""
    ranked, top, high, wait = board["ranked"], board["top"], board.get("high", []), board.get("high_wait", [])
    v = Counter(s["verdict"] for s in ranked)
    chase = v["Don't chase"]
    lead = ranked[0] if ranked else None
    log.done("ranker", "Ranker", "Scores every stock on six pillars into one Conviction",
             f"{len(ranked):,} stocks ranked",
             [f"#1 {lead['ticker']} at conviction {lead['conviction']:.0f}" if lead else "nothing to rank",
              "weights: " + " · ".join(f"{k} {w}" for k, w in cfg["pillars"].items())])
    earn = sum(1 for s in ranked if s.get("earnings_in_window"))
    log.done("risk", "Risk officer", "Vetoes weak businesses, wild swings, estimate cuts and bad timing",
             f"{v['Avoid']:,} avoided · {v['Limited upside']:,} limited upside",
             [f"{v['Watch']:,} on hold until the chart turns up or earnings pass",
              f"{chase:,} ran up too fast (don't chase)",
              f"{earn:,} report earnings inside the trade window"])
    log.done("planner", "Planner", "Builds entry, stop, target and exit date for each idea",
             f"{len(top)} top ideas · {len(high)} high-upside",
             [("top: " + ", ".join(s["ticker"] for s in top)) if top else "no stock passed every check",
              ("high-upside waiting: " + ", ".join(s["ticker"] for s in wait)) if wait else "no high-upside names waiting",
              f"{len(board['watch'])} on the watchlist"])


def write_changes(out: dict, ranked: list[dict]) -> None:
    """What changed since the previous trading day: new and dropped ideas,
    and every stock whose verdict (new buy or if-you-own-it) changed.
    Compares with the files from the last run before they're overwritten."""
    prev_board, prev_uni = DATA_OUT_DIR / "board.json", DATA_OUT_DIR / "universe.json"
    path = DATA_OUT_DIR / "changes.json"
    try:
        pb = json.loads(prev_board.read_text(encoding="utf-8"))
        pu = json.loads(prev_uni.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if pb.get("as_of") == out["as_of"]:          # same trading day (e.g. the morning re-run): keep the existing diff
        return
    ideas = lambda b: {s["ticker"]: s for s in b.get("top", []) + b.get("high", [])}
    old, new = ideas(pb), ideas(out)
    now = {s["ticker"]: s for s in ranked}
    was = {s["ticker"]: s for s in pu.get("stocks", [])}
    changes = {
        "since": pb.get("as_of"), "as_of": out["as_of"],
        "new_ideas": [{"ticker": t, "verdict": s.get("verdict"), "conviction": s.get("conviction")} for t, s in new.items() if t not in old],
        "dropped": [{"ticker": t, "now": now[t]["verdict"] if t in now else "not ranked", "why": now[t]["why"] if t in now else ""}
                    for t in old if t not in new],
        "verdicts": {t: {"was": was[t].get("verdict"), "now": s["verdict"], "hold_was": was[t].get("hold"), "hold_now": s["hold"],
                         "why": s["hold_why"]}
                     for t, s in now.items() if t in was and (was[t].get("verdict") != s["verdict"] or was[t].get("hold") != s["hold"])},
    }
    path.write_text(json.dumps(_round(changes), separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n")


def write(board: dict, price_data: dict, cfg: dict, universe_n: int) -> None:
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = board["ranked"]
    as_of = ranked[0]["as_of"] if ranked else date.today().isoformat()

    def full(s):
        d = {k: s.get(k) for k in COMPACT + ["timing_notes", "plan", "note", "earnings_in_window", "room_to_high", "as_of",
                                             "potential", "catalysts", "hu_score", "hu_ready", "upside_real", "target_low", "target_high"]}
        df = price_data.get(s["ticker"])
        d["chart"] = chart_data(df.loc[:s["as_of"]]) if df is not None else []
        return _round(d)

    spy = price_data.get("SPY")
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of, "universe_n": universe_n, "ranked_n": len(ranked),
        "market": market_weather(spy, spy.index[-1]) if spy is not None else None,
        "weights": cfg["pillars"], "rules": cfg["ideas"],
        "top": [full(s) for s in board["top"]],
        "watch": [full(s) for s in board["watch"]],
        "high": [full(s) for s in board.get("high", [])],
        "high_wait": [full(s) for s in board.get("high_wait", [])],
    }
    write_changes(out, ranked)          # before the old files are overwritten
    (DATA_OUT_DIR / "board.json").write_text(json.dumps(out, separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n")
    rows = [_round({k: s.get(k) for k in COMPACT}) for s in ranked]
    (DATA_OUT_DIR / "universe.json").write_text(json.dumps({"as_of": as_of, "stocks": rows}, separators=(",", ":"), allow_nan=False),
                                               encoding="utf-8", newline="\n")
    ins = board.get("insiders", {})
    notes = {s["ticker"]: brain.note(s, ins.get(s["ticker"])) for s in ranked}
    for s in board["top"] + board["watch"] + board.get("high", []) + board.get("high_wait", []):
        notes[s["ticker"]] = s["note"]
    (DATA_OUT_DIR / "notes.json").write_text(json.dumps(notes, separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n")
