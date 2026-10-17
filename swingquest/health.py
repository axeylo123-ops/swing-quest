"""Weekly System Health report ("The Reckoning").

1. Judges each scoring factor: did signals where it was STRONG beat the
   ones where it was weak (15-day return vs SPY)?
2. Proposes small, explainable changes: factor weights (+/-5 points),
   how much each kind of buyer counts, and the minimum score.
3. "What if": re-scores every past signal with the proposal and compares it
   with the current settings, separately on the older and newer half of the
   history. A proposal is only recommended if it wins in BOTH halves.
4. Writes docs/data/health.json and config/weights_proposed.yaml.
   It NEVER changes config/weights.yaml: you copy changes over yourself.
"""
import copy
import json
from datetime import date, datetime, timedelta, timezone

import yaml

from swingquest.backtest import scorecard
from swingquest.config import CONFIG_DIR, DATA_OUT_DIR, ROOT
from swingquest.signals.scoring import FACTORS, load_weights

HEALTH_FILE = DATA_OUT_DIR / "health.json"
PROPOSED_FILE = CONFIG_DIR / "weights_proposed.yaml"
EDGE = 0.005          # 0.5% difference in 15-day return vs SPY counts as real
STEP = 5              # weight change per suggestion
ROLE_STEP = 0.2
LABELS = {"cluster": "Insider cluster", "role": "Buyer's rank", "dollar_size": "Gold committed ($)",
          "stake_increase": "Stake increase", "first_buy": "First buy in a year", "price_context": "Near 52-week low"}


def verdict(f: dict) -> str:
    if not f["enough_data"] or f["edge_excess_15"] is None:
        return "not enough data"
    if f["edge_excess_15"] >= EDGE:
        return "helping"
    if f["edge_excess_15"] <= -EDGE:
        return "hurting"
    return "unclear"


# ---------------------------------------------------------------- re-scoring
def rescore(row: dict, cfg_now: dict, cfg_new: dict) -> dict:
    """Score a past signal again under new settings. Each factor's earned
    fraction is recovered from its points; role uses the new role_points."""
    w_now, w_new = cfg_now["weights"], cfg_new["weights"]
    total = 0.0
    for f in FACTORS:
        if f == "role":
            frac = cfg_new["role_points"].get(row["role"], 0)
        else:
            frac = (row.get(f"{f}_points") or 0) / w_now[f] if w_now[f] else 0
        total += w_new[f] * frac
    score = max(0, min(100, round(total)))
    min_score = cfg_new["rules"]["min_score"]
    status = ("pick" if score >= min_score and row["timing"] == "Ready"
              else "watch" if score >= min_score else "below")
    return {**row, "score": score, "status": status}


def split_halves(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    dates = sorted(r["signal_date"] for r in scorecard.finished(rows))
    if not dates:
        return [], []
    mid = dates[len(dates) // 2]
    return [r for r in rows if r["signal_date"] < mid], [r for r in rows if r["signal_date"] >= mid]


def months_covered(rows: list[dict]) -> float:
    dates = sorted(r["signal_date"] for r in scorecard.finished(rows))
    if len(dates) < 2:
        return 1.0
    return max(1.0, (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 30.4)


def pick_stats(rows, cfg_now, cfg) -> dict:
    """Quest (pick) results under a config, overall and per half, plus
    quests per month and the 'worst half' (the robust yardstick)."""
    scored = [rescore(r, cfg_now, cfg) for r in rows]
    older, newer = split_halves(scored)
    s = lambda rs: scorecard.stats([r for r in rs if r["status"] == "pick"])
    keep = ("n", "win_rate", "avg_trade_return", "avg_excess_15", "enough_data")
    out = {k: {f: v[f] for f in keep} for k, v in (("all", s(scored)), ("older", s(older)), ("newer", s(newer)))}
    out["per_month"] = round(out["all"]["n"] / months_covered(rows), 1)
    halves = [out[h]["avg_excess_15"] for h in ("older", "newer")]
    judged = all(out[h]["enough_data"] for h in ("older", "newer")) and None not in halves
    out["worst_half"] = min(halves) if judged else None
    return out


def best_threshold(rows, cfg_now, cfg, target: float) -> tuple[int, dict]:
    """Minimum score that gives about `target` quests a month (at most 25% more)
    with the best WORST-half result. Judging by the weaker half keeps us from
    chasing a lucky streak."""
    best_m, best = cfg["rules"]["min_score"], None
    for m in range(50, 90, 5):
        trial = copy.deepcopy(cfg)
        trial["rules"]["min_score"] = m
        st = pick_stats(rows, cfg_now, trial)
        if st["worst_half"] is None or st["per_month"] > target * 1.25:
            continue
        if best is None or st["worst_half"] > best["worst_half"]:
            best_m, best = m, st
    return best_m, best


# ---------------------------------------------------------------- proposals
def propose(rows: list[dict], cfg: dict) -> tuple[dict, list[dict], list[dict]]:
    weights = cfg["weights"]
    table = scorecard.factor_table(rows, weights)
    factors = [{"name": f, "label": LABELS[f], "weight": weights[f], "edge": t["edge_excess_15"],
                "with_n": t["with"]["n"], "without_n": t["without"]["n"], "verdict": verdict(t)} for f, t in table.items()]

    new = copy.deepcopy(cfg)
    why: dict[str, str] = {}
    for f in factors:
        if f["name"] == "role":
            continue  # role is tuned through role_points below
        if f["verdict"] == "helping":
            new["weights"][f["name"]] = min(40, weights[f["name"]] + STEP)
            why[f["name"]] = f"strong signals beat weak ones by {f['edge'] * 100:+.1f}%"
        elif f["verdict"] == "hurting":
            new["weights"][f["name"]] = max(0, weights[f["name"]] - STEP)
            why[f["name"]] = f"strong signals did worse than weak ones ({f['edge'] * 100:+.1f}%)"
    new["weights"] = normalize(new["weights"])

    by_role = scorecard.group(rows, lambda r: r["role"])
    overall = scorecard.stats(rows)["avg_excess_15"] or 0
    for role, s in by_role.items():
        if not s["enough_data"] or s["avg_excess_15"] is None or role not in new["role_points"]:
            continue
        cur = cfg["role_points"][role]
        if s["avg_excess_15"] >= overall + 0.01 and cur < 1.0:
            new["role_points"][role] = round(min(1.0, cur + ROLE_STEP), 2)
            why[f"role:{role}"] = f"{role} buys beat the average signal by {(s['avg_excess_15'] - overall) * 100:+.1f}%"
        elif s["avg_excess_15"] <= overall - 0.01 and cur > 0.2:
            new["role_points"][role] = round(max(0.1, cur - ROLE_STEP), 2)
            why[f"role:{role}"] = f"{role} buys trailed the average signal by {(s['avg_excess_15'] - overall) * 100:+.1f}%"

    # Choose between keeping today's weights and the adjusted ones, each with
    # its best minimum score for your quests-per-month goal.
    target = cfg["rules"].get("quests_per_month", 4)
    keep_m, keep_st = best_threshold(rows, cfg, cfg, target)
    adj_m, adj_st = best_threshold(rows, cfg, new, target)
    if adj_st is None or (keep_st is not None and keep_st["worst_half"] >= adj_st["worst_half"]):
        new = copy.deepcopy(cfg)          # weight changes don't help robustly: keep them as they are
        why = {}
        best_m, best_st = keep_m, keep_st
    else:
        best_m, best_st = adj_m, adj_st
    if best_st is not None and best_m != cfg["rules"]["min_score"]:
        new["rules"]["min_score"] = best_m
        why["min_score"] = (f"about {best_st['per_month']} quests a month (your goal: {target}); the weaker half of the "
                            f"history still beat SPY by {best_st['worst_half'] * 100:+.1f}%")

    suggestions = []
    for f in FACTORS:
        if new["weights"][f] != weights[f]:
            suggestions.append({"factor": f, "label": f"{LABELS[f]} weight", "current": weights[f],
                                "suggested": new["weights"][f], "why": why.get(f, "rebalanced so weights add to 100")})
    for role, v in new["role_points"].items():
        if v != cfg["role_points"][role]:
            suggestions.append({"factor": f"role_points.{role}", "label": f"Points for a {role}", "current": cfg["role_points"][role],
                                "suggested": v, "why": why.get(f"role:{role}", "")})
    if new["rules"]["min_score"] != cfg["rules"]["min_score"]:
        suggestions.append({"factor": "rules.min_score", "label": "Minimum score for a quest", "current": cfg["rules"]["min_score"],
                            "suggested": new["rules"]["min_score"], "why": why["min_score"]})
    return new, factors, suggestions


def normalize(w: dict) -> dict:
    """Scale to add up to exactly 100 (whole numbers)."""
    total = sum(w.values()) or 1
    out = {k: round(v * 100 / total) for k, v in w.items()}
    out[max(out, key=out.get)] += 100 - sum(out.values())
    return out


# ---------------------------------------------------------------- report
def observations(rows: list[dict], live_rows: list[dict]) -> tuple[list[str], list[str]]:
    obs, todo = [], []
    picks = scorecard.stats([r for r in rows if r["status"] == "pick"])
    if picks["n_trades"]:
        obs.append(f"Quest exits: target first {picks['target_first']:.0%}, stop first {picks['stop_first']:.0%}, "
                   f"15-day time limit {picks['time_exit']:.0%}.")
        if picks["time_exit"] and picks["time_exit"] > 0.5:
            todo.append("Most quests end at the 15-day limit before reaching the target. Worth testing a closer target "
                        "(e.g. a 1.5 x ATR stop instead of 2 x, which keeps the 2:1 ratio) in settings.yaml.")
    bands = [("under $5", lambda r: (r.get("entry") or 0) < 5), ("$5-$30", lambda r: 5 <= (r.get("entry") or 0) <= 30),
             ("over $30", lambda r: (r.get("entry") or 0) > 30)]
    parts = []
    for name, f in bands:
        s = scorecard.stats([r for r in rows if f(r)])
        if s["n"] and s["avg_excess_15"] is not None:
            parts.append(f"{name}: {s['avg_excess_15'] * 100:+.1f}% vs SPY ({s['n']} signals)")
    if parts:
        obs.append("By share price, " + "; ".join(parts) + ".")
    live_q = [r for r in live_rows if r["status"] == "pick"]
    done = scorecard.finished(live_q)
    obs.append(f"Live tracking: {len(live_rows)} signals logged, {len(live_q)} quests, {len(done)} finished.")
    if len(done) < scorecard.MIN_SAMPLES:
        todo.append(f"Live results are still building ({len(done)}/{scorecard.MIN_SAMPLES} finished quests). "
                    "Until then, judgments lean on the backtest, which flatters results (delisted stocks are missing).")
    return obs, todo


def build_report(backtest_rows: list[dict], live_rows: list[dict], today: date | None = None) -> tuple[dict, dict]:
    cfg = load_weights()
    rows = backtest_rows + live_rows
    new, factors, suggestions = propose(rows, cfg)
    now, prop = pick_stats(rows, cfg, cfg), pick_stats(rows, cfg, new)
    # recommended only if the weaker half of history improves (robust, not a lucky streak)
    robust = bool(suggestions) and prop["worst_half"] is not None and (
        now["worst_half"] is None or prop["worst_half"] > now["worst_half"])
    obs, todo = observations(rows, live_rows)
    obs.insert(0, f"Today's settings give about {now['per_month']} quests a month; your goal is "
                  f"{cfg['rules'].get('quests_per_month', 4)}.")
    if suggestions and not robust:
        todo.append("The suggested changes did not improve the weaker half of the history, "
                    "so they are shown for interest only. Keep the current settings.")
    today = today or datetime.now(timezone.utc).date()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "week": (today - timedelta(days=today.weekday())).isoformat(),
        "factors": factors,
        "suggestions": suggestions,
        "recommended": robust,
        "whatif": {"current": now, "proposed": prop},
        "observations": obs,
        "improvements": todo,
        "sources": {"backtest_signals": len(backtest_rows), "live_signals": len(live_rows)},
    }
    return report, new


def write_report(report: dict, proposed_cfg: dict) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(report, indent=1), encoding="utf-8", newline="\n")
    header = [
        "# PROPOSED weights from the weekly System Health report (" + report["week"] + ").",
        "# NOTHING here is used by the scanner. To accept, copy the values you agree",
        "# with into config/weights.yaml yourself.",
        "# Recommended: " + ("YES - beat the current settings in both halves of the history."
                             if report["recommended"] else "NO - not better in both halves; for interest only."),
    ]
    for s in report["suggestions"]:
        header.append(f"#   {s['label']}: {s['current']} -> {s['suggested']}  ({s['why']})")
    if not report["suggestions"]:
        header.append("#   No changes suggested this week.")
    PROPOSED_FILE.write_text("\n".join(header) + "\n\n" + yaml.safe_dump(proposed_cfg, sort_keys=False),
                             encoding="utf-8", newline="\n")


def run() -> dict:
    from swingquest.backtest.report import ROWS_FILE
    from swingquest.tracker import load_log
    bt = json.loads(ROWS_FILE.read_text(encoding="utf-8")) if ROWS_FILE.exists() else []
    report, new = build_report(bt, load_log())
    write_report(report, new)
    return report
