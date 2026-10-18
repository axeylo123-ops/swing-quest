"""The Insiders pillar: genuine open-market conviction buying only.

Cleans out purchases that look like insider buying but aren't conviction:
  - price mismatch: paid far from the market price that day (company plans,
    option-related deals, or a different share class)
  - plan clusters: 3+ insiders buying the exact same dollar amount on the
    same day (director share plans)
  - pre-scheduled 10b5-1 plan buys
Then scores what's left from 50 (no genuine buying: neutral, not negative)
up to 100 (a strong cluster of senior insiders with big money).
"""
from collections import defaultdict

import pandas as pd

from swingquest.signals import scoring

WINDOW_DAYS = 60
PRICE_BAND = (0.85, 1.18)   # market close / price paid
ROLE_POINTS = {"CEO": 1.0, "CFO": 1.0, "Director": 0.7, "Officer": 0.5, "10% Owner": 0.6, "Other": 0.2}


def clean(buys: list[dict], prices: pd.DataFrame | None) -> tuple[list[dict], list[dict]]:
    """Returns (genuine buys, excluded buys with a plain reason)."""
    genuine, excluded = [], []
    same_day = defaultdict(list)
    for b in buys:
        same_day[(b["filed_date"], round(b["value"], -2))].append(b)
    plan_keys = {k for k, v in same_day.items() if len({x["owner_cik"] for x in v}) >= 3}
    for b in buys:
        if b.get("plan_10b5_1"):
            excluded.append({**b, "why": "pre-scheduled 10b5-1 plan"})
            continue
        if (b["filed_date"], round(b["value"], -2)) in plan_keys:
            excluded.append({**b, "why": "identical same-day purchases by several insiders (likely a company plan)"})
            continue
        if prices is not None and len(prices):
            past = prices["close"].loc[:pd.Timestamp(b.get("trade_date") or b["filed_date"])]
            if len(past):
                ratio = float(past.iloc[-1]) / b["avg_price"]
                if not PRICE_BAND[0] <= ratio <= PRICE_BAND[1]:
                    excluded.append({**b, "why": f"paid ${b['avg_price']:.2f} vs market ${float(past.iloc[-1]):.2f} "
                                                 "(plan, option deal or other share class)"})
                    continue
        genuine.append(b)
    return genuine, excluded


def pillar(buys: list[dict], prices: pd.DataFrame | None, prior: list[dict] | None = None,
           history_start: str | None = None) -> dict:
    """Insiders pillar score (50-100) with the facts behind it."""
    genuine, excluded = clean(buys, prices)
    if not genuine:
        return {"score": 50, "genuine": [], "excluded": excluded, "facts": None}
    cl = scoring.cluster(genuine)["fraction"]
    ro = max(ROLE_POINTS.get(b["role"], 0.2) for b in genuine)
    dl = scoring.dollar_size(genuine)["fraction"]
    st = scoring.stake_increase(genuine)["fraction"]
    fb = scoring.first_buy(genuine, prior or [], history_start)["fraction"]
    strength = 0.30 * cl + 0.25 * ro + 0.20 * dl + 0.15 * st + 0.10 * fb
    people = {b["owner_cik"]: b for b in genuine}
    rank = list(ROLE_POINTS)
    top = min(genuine, key=lambda b: (rank.index(b["role"]) if b["role"] in rank else 99, -b["value"]))  # most senior, then biggest
    facts = {
        "insiders": len(people),
        "dollars": round(sum(b["value"] for b in genuine), 2),
        "top_role": top["role"],
        "top_name": top["owner_name"],
        "last_filed": max(b["filed_date"] for b in genuine),
        "avg_price": round(sum(b["value"] for b in genuine) / sum(b["shares"] for b in genuine), 2)
                     if all(b.get("shares") for b in genuine) else None,
    }
    return {"score": round(50 + 50 * strength), "genuine": genuine, "excluded": excluded, "facts": facts}
