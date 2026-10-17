"""The insider score (0-100).

Each factor returns a fraction between 0 and 1 (how much of its weight it
earns), the raw value (for the scorecard), and a plain-English reason.
The score only uses insider facts plus the 52-week price context; chart
timing is kept separate (see plan.py) so the scorecard can judge each
part on its own.
"""
from datetime import date, timedelta

from swingquest.config import load_yaml

FACTORS = ["cluster", "role", "dollar_size", "stake_increase", "first_buy", "price_context"]
ROLE_WORDS = {"CEO": "the CEO", "CFO": "the CFO", "Director": "a director",
              "Officer": "an officer", "10% Owner": "a 10% owner (big investor)", "Other": "an insider"}


def load_weights() -> dict:
    cfg = load_yaml("weights.yaml")
    total = sum(cfg["weights"].values())
    if abs(total - 100) > 1e-9:
        raise ValueError(f"weights in config/weights.yaml add up to {total}, not 100")
    return cfg


def _money(x: float) -> str:
    return f"${x / 1e6:.1f}M" if x >= 1e6 else f"${x / 1e3:.0f}K"


def _step(value: float, steps: list[tuple[float, float]]) -> float:
    """First fraction whose threshold `value` reaches; steps sorted high->low."""
    for threshold, fraction in steps:
        if value >= threshold:
            return fraction
    return 0.0


def cluster(buys: list[dict]) -> dict:
    n = len({b["owner_cik"] for b in buys})
    frac = 1.0 if n >= 3 else 0.6 if n == 2 else 0.0
    reason = f"{n} different insiders bought in the last 30 days" if n >= 2 else None
    return {"fraction": frac, "value": n, "reason": reason}


def role(buys: list[dict], role_points: dict) -> dict:
    best = max((b["role"] for b in buys), key=lambda r: role_points.get(r, 0))
    return {"fraction": role_points.get(best, 0), "value": best,
            "reason": f"Buyers include {ROLE_WORDS.get(best, best)}"}


def dollar_size(buys: list[dict]) -> dict:
    total = sum(b["value"] for b in buys)
    frac = _step(total, [(1e6, 1.0), (5e5, 0.8), (2.5e5, 0.6), (1e5, 0.3)])
    return {"fraction": frac, "value": round(total, 2),
            "reason": f"{_money(total)} bought in total" if frac > 0 else None}


def stake_increase(buys: list[dict]) -> dict:
    """Biggest stake increase among the buyers. A brand-new position counts
    well; unknown holdings earn nothing."""
    best, best_buy, new_position = None, None, False
    for b in buys:
        if b.get("holdings_before") == 0:
            new_position = True
        p = b.get("pct_of_holdings")
        if p is not None and (best is None or p > best):
            best, best_buy = p, b
    if best is not None and best >= 0.2:
        frac = _step(best, [(0.5, 1.0), (0.2, 0.75)])
    elif new_position:
        return {"fraction": 0.7, "value": None, "reason": "An insider opened a brand-new position"}
    elif best is not None:
        frac = _step(best, [(0.1, 0.5), (0.05, 0.25)])
    else:
        return {"fraction": 0.0, "value": None, "reason": None}
    who = ROLE_WORDS.get(best_buy["role"], "an insider")
    reason = f"{who[0].upper() + who[1:]} grew their stake by {best:.0%}" if frac > 0 else None
    return {"fraction": frac, "value": round(best, 4), "reason": reason}


def first_buy(buys: list[dict], prior_buys: list[dict], history_start: str | None) -> dict:
    """1.0 if any buyer had no purchase in this stock in the 12 months
    before their first buy in the window. Needs a year of stored history;
    without it the factor is 'unknown' and earns nothing."""
    earliest_needed = min(b["filed_date"] for b in buys)
    year_before = (date.fromisoformat(earliest_needed) - timedelta(days=365)).isoformat()
    if history_start is None or history_start > year_before:
        return {"fraction": 0.0, "value": None, "known": False,
                "reason": None, "caution": "Not enough history yet to check for a first buy in 12 months"}
    for owner in {b["owner_cik"] for b in buys}:
        first = min(b["filed_date"] for b in buys if b["owner_cik"] == owner)
        start = (date.fromisoformat(first) - timedelta(days=365)).isoformat()
        if not any(p["owner_cik"] == owner and start <= p["filed_date"] < first for p in prior_buys):
            r = next(b["role"] for b in buys if b["owner_cik"] == owner)
            return {"fraction": 1.0, "value": True, "known": True,
                    "reason": f"First purchase in over 12 months by {ROLE_WORDS.get(r, r)}"}
    return {"fraction": 0.0, "value": False, "known": True, "reason": None}


def price_context(snap: dict) -> dict:
    pos = snap["range_position"]
    frac = 1.0 if pos <= 0.10 else 0.6 if pos <= 0.25 else 0.3 if pos <= 0.40 else 0.0
    reason = (f"Trading near its 52-week low ({pos:.0%} of the way up from the low)"
              if frac > 0 else None)
    return {"fraction": frac, "value": round(pos, 4), "reason": reason}


def score(buys: list[dict], prior_buys: list[dict], history_start: str | None,
          snap: dict, cfg: dict) -> dict:
    """Returns {'score': 0-100, 'factors': {...}, 'reasons': [...], 'cautions': [...]}."""
    factors = {
        "cluster": cluster(buys),
        "role": role(buys, cfg["role_points"]),
        "dollar_size": dollar_size(buys),
        "stake_increase": stake_increase(buys),
        "first_buy": first_buy(buys, prior_buys, history_start),
        "price_context": price_context(snap),
    }
    weights = cfg["weights"]
    for name, f in factors.items():
        f["points"] = round(weights[name] * f["fraction"], 1)
    total = round(sum(f["points"] for f in factors.values()))
    return {
        "score": max(0, min(100, total)),
        "factors": factors,
        "reasons": [f["reason"] for f in factors.values() if f.get("reason")],
        "cautions": [f["caution"] for f in factors.values() if f.get("caution")],
    }
