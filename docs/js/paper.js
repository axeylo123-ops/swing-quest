// Paper trading engine: $100 practice trades graded with the same rules as the
// Record (and the Python backtest), so your bubbles and the system's are comparable.
//
//   - you buy at the next market open after you click (no peeking at prices you've seen)
//   - the plan's stop and target decide the exit; if both are touched the same day, the stop counts
//   - an overnight gap through the stop or target exits at that (worse or better) opening price
//   - otherwise it sells at the close of the last day of the plan's time limit
// Pure functions only (no page code), so it can be tested outside the browser.

export const START = 100;                     // every bubble starts as $100
const KEY = "sq.paper.v1";

// ---- when an order placed now gets filled: today's open if it's a weekday before 9:30 New York time, else the next weekday
export function fillOn(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short",
  }).formatToParts(now).map((p) => [p.type, p.value]));
  const day = `${parts.year}-${parts.month}-${parts.day}`;
  const weekend = parts.weekday === "Sat" || parts.weekday === "Sun";
  if (!weekend && +parts.hour * 60 + +parts.minute < 570) return day;
  return nextWeekday(day);
}

export function nextWeekday(day) {
  const [y, m, d] = day.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  do t.setUTCDate(t.getUTCDate() + 1); while (t.getUTCDay() === 0 || t.getUTCDay() === 6);
  return t.toISOString().slice(0, 10);
}

// ---- grade one trade. bars = [[date, open, high, low, close], ...] oldest first.
// opts.strict: skip if it opens above the buy zone (the system's rule; your own orders always fill)
// opts.closeOn: you sold it yourself at that day's close
export function simulate(bars, plan, fill, opts = {}) {
  if (!bars?.length) return { status: "nodata" };
  const i = bars.findIndex((b) => b[0] >= fill);
  if (i < 0) return { status: "pending", fillOn: fill };
  if (i === 0 && bars[0][0] > fill && !opts.allowLateStart) return { status: "nodata" };
  const entry = bars[i][1], entryDate = bars[i][0], { stop, target } = plan, max = plan.time_stop_days || 15;
  const base = { entry, entryDate, stop, target, timeStop: max, aboveZone: entry > plan.entry_high };
  if (opts.strict && entry > plan.entry_high) return { ...base, status: "skipped", reason: "opened above the buy zone" };
  if (entry <= stop) return { ...base, status: "skipped", reason: "opened below the stop: order cancelled" };
  const path = [];
  const done = (k, price, reason) => {
    path.push([bars[i + k][0], round(START * price / entry)]);
    return { ...base, status: "closed", reason, exitDate: bars[i + k][0], exitPrice: price, days: k + 1,
      ret: price / entry - 1, value: round(START * price / entry), path };
  };
  const n = Math.min(max, bars.length - i);
  for (let k = 0; k < n; k++) {
    const [d, o, h, l, c] = bars[i + k];
    if (opts.closeOn && d >= opts.closeOn) return done(k, c, "sold");
    if (k > 0) {
      if (o <= stop) return done(k, o, "stop");
      if (o >= target) return done(k, o, "target");
    }
    if (l <= stop) return done(k, stop, "stop");
    if (h >= target) return done(k, target, "target");
    path.push([d, round(START * c / entry)]);
  }
  if (bars.length - i < max) {
    const last = bars.at(-1);
    return { ...base, status: "open", days: bars.length - i, lastDate: last[0], price: last[4],
      ret: last[4] / entry - 1, value: round(START * last[4] / entry), path };
  }
  path.pop();
  return done(max - 1, bars[i + max - 1][4], "time");
}

const round = (x) => Math.round(x * 100) / 100;

// Market return over the same days (SPY, open of entry day to close of exit or last day).
export function marketReturn(spy, from, to) {
  if (!spy?.length || !from) return null;
  const a = spy.find((b) => b[0] >= from), z = [...spy].reverse().find((b) => b[0] <= (to || spy.at(-1)[0]));
  return a && z && z[0] >= a[0] ? z[4] / a[1] - 1 : null;
}

// Value of a graded trade on a given day (for the replay): null if not started, "popped" day = exit day.
export function valueOn(g, day) {
  if (!g.path?.length || day < g.path[0][0]) return null;
  if (g.exitDate && day > g.exitDate) return null;
  let v = null;
  for (const [d, x] of g.path) { if (d <= day) v = x; else break; }
  return v;
}

// ---- the system's own picks (from data/paper.json): graded here when bars exist, else the bot's grade
export function gradeSystem(pick, bars) {
  const fill = nextDay(pick.signal_date);
  const g = bars ? simulate(bars, pick.plan, fill, { strict: true }) : { status: "nodata" };
  if (g.status !== "nodata") return g;
  if (pick.exit_reason === "skipped") return { status: "skipped", reason: pick.skip_reason };
  if (["target", "stop", "time"].includes(pick.exit_reason) && pick.entry) {
    return { status: "closed", reason: pick.exit_reason, entry: pick.entry, entryDate: pick.entry_date, exitDate: pick.exit_date,
      exitPrice: pick.exit_price, ret: pick.trade_return, value: round(START * (1 + pick.trade_return)), path: [] };
  }
  return { status: "nodata" };
}

export function nextDay(day) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

// ---- your trades, stored only in this browser
export function load(store = globalThis.localStorage) {
  try { return JSON.parse(store.getItem(KEY))?.trades || []; } catch { return []; }
}
export function save(trades, store = globalThis.localStorage) {
  try { store.setItem(KEY, JSON.stringify({ trades })); } catch { /* storage blocked: nothing saved */ }
}

export function newTrade(s, why, now = new Date()) {
  const p = s.plan;
  return {
    id: `${s.ticker}-${now.getTime()}`, ticker: s.ticker, name: s.name || "", currency: s.currency || "USD",
    placedAt: now.toISOString(), fillOn: fillOn(now), conviction: s.conviction, verdict: s.verdict,
    plan: { entry_low: p.entry_low, entry_high: p.entry_high, stop: p.stop, target: p.target,
      time_stop_days: p.time_stop_days, reference: p.reference ?? s.price },
    why: (why || "").trim().slice(0, 140),
  };
}

// Grades every trade; a finished result is kept with the trade so it survives prices rolling out of the feed.
export function gradeMine(trades, bars) {
  let changed = false;
  const out = trades.map((t) => {
    if (t.result) return { t, g: t.result };
    const g = simulate(bars?.[t.ticker], t.plan, t.fillOn, { closeOn: t.closeOn });
    if (g.status === "closed" || g.status === "skipped") { t.result = g; changed = true; }
    return { t, g };
  });
  return { graded: out, changed };
}

// Totals for a set of graded trades.
export function totals(list, spy) {
  const closed = list.filter((x) => x.g.status === "closed"), open = list.filter((x) => x.g.status === "open");
  const won = closed.filter((x) => x.g.ret > 0).length;
  const pl = closed.reduce((a, x) => a + (x.g.value - START), 0);
  const mkt = closed.map((x) => marketReturn(spy, x.g.entryDate, x.g.exitDate)).filter((v) => v != null);
  const avg = closed.length ? closed.reduce((a, x) => a + x.g.ret, 0) / closed.length : null;
  return {
    open: open.length, pending: list.filter((x) => x.g.status === "pending").length, closed: closed.length, won,
    pl: round(pl), openValue: round(open.reduce((a, x) => a + x.g.value, 0)), avg,
    vsMarket: avg != null && mkt.length === closed.length ? avg - mkt.reduce((a, b) => a + b, 0) / mkt.length : null,
  };
}
