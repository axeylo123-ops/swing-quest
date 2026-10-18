"""Runs the brain end to end and writes what the dashboard reads:

docs/data/board.json     top ideas + watchlist (full notes, charts, plans)
docs/data/universe.json  every ranked stock, compact (search, sorting, your holdings)
docs/data/notes.json     analyst-style notes for every ranked stock (loaded on demand)
"""
import json
from datetime import date, datetime, timedelta, timezone

from swingquest import brain, events, fundamentals, insider_signal, stocklist, store
from swingquest.config import DATA_OUT_DIR, settings
from swingquest.prices.base import get_price_source
from swingquest.signals.scan import chart_data, market_weather
from swingquest.signals.scoring import load_weights
from swingquest.universe import exchange_map, is_us_listed

INSIDER_DAYS = 60
COMPACT = ["ticker", "name", "country", "sector", "industry", "currency", "price", "mcap", "conviction", "rank",
           "pillars", "penalty", "verdict", "why", "hold", "hold_why", "analyst_upside", "n_analysts", "target",
           "swing_upside", "timing", "rs_3m", "fpe", "flags"]


def _round(x):
    if isinstance(x, float):
        return round(x, 4)
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
    stocks = universe_with_insider_names(buys)
    tickers = [s["ticker"] for s in stocks]
    progress(f"Universe: {len(stocks)} stocks")
    if fetch:
        progress(f"Refreshing fundamentals (up to {info_budget} stalest)...")
        fundamentals.refresh_info(tickers, budget=info_budget, progress=progress)
    progress("Loading prices...")
    price_data = get_price_source().history(tickers + ["SPY"], today - timedelta(days=420), today)
    hist_start = store.load_state().get("history_start")
    ins = insider_scores(buys, prior, price_data, hist_start)

    def build(earn=None):
        return brain.build_board(stocks, fundamentals.load(), price_data, ins, cfg, trade_cfg, earnings_lookup=earn)

    board = build()
    if fetch:   # estimate revisions + earnings surprises for the leaders, then rebuild with earnings dates
        progress("Refreshing earnings estimates for the leaders...")
        fundamentals.refresh_estimates([s["ticker"] for s in board["ranked"][:150]], progress=progress)
    board = build(events.earnings_dates if fetch else events.cached_dates)
    board["insiders"] = ins
    write(board, price_data, cfg, len(stocks))
    t = board["top"]
    progress(f"Ranked {len(board['ranked'])} stocks. Top ideas: " + (", ".join(f"{s['ticker']} ({s['conviction']})" for s in t) or "none today"))
    return board


def write(board: dict, price_data: dict, cfg: dict, universe_n: int) -> None:
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = board["ranked"]
    as_of = ranked[0]["as_of"] if ranked else date.today().isoformat()

    def full(s):
        d = {k: s.get(k) for k in COMPACT + ["timing_notes", "plan", "note", "earnings_in_window", "room_to_high", "as_of"]}
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
    }
    (DATA_OUT_DIR / "board.json").write_text(json.dumps(out, separators=(",", ":"), allow_nan=False), encoding="utf-8", newline="\n")
    rows = [_round({k: s.get(k) for k in COMPACT}) for s in ranked]
    (DATA_OUT_DIR / "universe.json").write_text(json.dumps({"as_of": as_of, "stocks": rows}, separators=(",", ":"), allow_nan=False),
                                               encoding="utf-8", newline="\n")
    ins = board.get("insiders", {})
    notes = {s["ticker"]: brain.note(s, ins.get(s["ticker"])) for s in ranked}
    for s in board["top"] + board["watch"]:
        notes[s["ticker"]] = s["note"]
    (DATA_OUT_DIR / "notes.json").write_text(json.dumps(notes, separators=(",", ":")), encoding="utf-8", newline="\n")
