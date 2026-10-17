// Past finished signals (docs/data/history.json) and the questions we ask them:
// "how did quests like this one do?" and "Ask the Oracle" filters.
import { tierOf } from "./art.js";

export const MIN_SAMPLES = 30;
export const ROLE_GROUPS = {
  "CEO / CFO": (r) => r === "CEO" || r === "CFO",
  "Director": (r) => r === "Director",
  "10% owner": (r) => r === "10% Owner",
  "Other officer": (r) => r === "Officer" || r === "Other",
};
export const roleGroup = (role) => Object.keys(ROLE_GROUPS).find((g) => ROLE_GROUPS[g](role)) || "Other officer";

export function rows(history) {
  if (!history) return [];
  const f = history.fields;
  return history.rows.map((r) => Object.fromEntries(f.map((k, i) => [k, r[i]])));
}

const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

export function summarize(list) {
  const trades = list.filter((r) => r.taken && r.trade_return != null);
  return {
    n: list.length,
    trades: trades.length,
    win: trades.length ? trades.filter((r) => r.trade_return > 0).length / trades.length : null,
    avgTrade: avg(trades.map((r) => r.trade_return)),
    vsMarket: avg(list.map((r) => r.excess_15)),
    beat: list.length ? list.filter((r) => r.excess_15 > 0).length / list.length : null,
    enough: list.length >= MIN_SAMPLES,
  };
}

// Quests like this one: same rarity tier and same kind of top buyer.
export function similar(all, score, role) {
  const tier = tierOf(score).name, group = roleGroup(role);
  const list = all.filter((r) => tierOf(r.score).name === tier && roleGroup(r.role) === group);
  return { tier, group, ...summarize(list) };
}

export function since(all, monthsBack, end) {
  const d = new Date(end);
  d.setMonth(d.getMonth() - monthsBack);
  const cut = d.toISOString().slice(0, 10);
  return all.filter((r) => r.signal_date >= cut);
}
