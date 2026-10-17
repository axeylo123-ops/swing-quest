// The game layer: XP, levels, streaks, quests. Stored only in this browser.
// XP rewards good habits (checking in, reviewing, following your rules),
// never the number of trades.
import { storage, todayStr, parseDay, isWeekday, weekKey, esc, ICONS, shortDate } from "./util.js";

const KEY = "sq.game.v1";
export const XP = { checkin: 10, quiet: 5, review: 5, rules: 15, health: 25 };
const TITLES = ["Rookie Scout", "Chart Apprentice", "Insider Tracker", "Patient Hunter",
  "Swing Ranger", "Signal Sage", "Market Monk", "Quest Master"];

// Add new quests by adding an entry here. `value` reads progress from the saved state.
export const QUESTS = [
  { id: "first-steps", title: "First Steps", desc: "Check in for the first time", goal: 1, xp: 20, value: (s) => s.checkins.length },
  { id: "week-warrior", title: "Week Warrior", desc: "Reach a 5-day check-in streak", goal: 5, xp: 50, value: (s) => s.best },
  { id: "month-discipline", title: "Month of Discipline", desc: "Reach a 20-day check-in streak", goal: 20, xp: 200, value: (s) => s.best },
  { id: "careful-reader", title: "Careful Reader", desc: "Review 10 pick cards", goal: 10, xp: 50, value: (s) => Object.keys(s.reviewed).length },
  { id: "rule-keeper", title: "Rule Keeper", desc: "Complete 5 rule checks (passing on a trade counts)", goal: 5, xp: 75, value: (s) => Object.keys(s.ruleChecks).length },
  { id: "patience", title: "Patience Pays", desc: "Check in on 5 \"No setups\" days without forcing a trade", goal: 5, xp: 50, value: (s) => s.quietDays.length },
  { id: "health-inspector", title: "Health Inspector", desc: "Read 4 weekly System Health reports", goal: 4, xp: 100, value: (s) => s.healthWeeks.length },
  { id: "know-holdings", title: "Know Your Holdings", desc: "Import your portfolio CSV (it never leaves this browser)", goal: 1, xp: 20, value: (s) => (s.flags.portfolio ? 1 : 0) },
];

const blank = () => ({
  xp: 0, checkins: [], quietDays: [], reviewed: {}, ruleChecks: {}, healthWeeks: [], quests: [],
  streak: 0, best: 0, shields: 1, shieldWeek: null, last: null, log: [], flags: {},
});
let state = { ...blank(), ...storage.get(KEY, {}) };
const listeners = [];
export const onChange = (fn) => listeners.push(fn);
export const get = () => state;
function save() { storage.set(KEY, state); listeners.forEach((fn) => fn(state)); }

// Level L starts at 50 * L * (L - 1) XP: 0, 100, 300, 600, 1000, 1500...
const needFor = (L) => 50 * L * (L - 1);
export function level(xp = state.xp) {
  let L = 1;
  while (xp >= needFor(L + 1)) L++;
  return { level: L, title: TITLES[Math.min(L - 1, TITLES.length - 1)], into: xp - needFor(L), span: needFor(L + 1) - needFor(L) };
}

function award(points, why) {
  const before = level().level;
  state.xp += points;
  state.log.unshift({ d: todayStr(), points, why });
  state.log = state.log.slice(0, 40);
  toast(`+${points} XP`, why);
  const after = level();
  if (after.level > before) toast(`Level up! Level ${after.level}`, after.title);
}

function checkQuests() {
  for (const q of QUESTS) {
    if (!state.quests.includes(q.id) && q.value(state) >= q.goal) {
      state.quests.push(q.id);
      award(q.xp, `Quest complete: ${q.title}`);
    }
  }
}

// Streaks count weekdays. Each week refills one "shield" (max 2) that covers a
// missed weekday (holidays, busy days), so one slip doesn't wipe your streak.
function updateStreak(day) {
  const wk = weekKey(day);
  if (state.shieldWeek !== wk) { state.shields = Math.min(2, (state.shields ?? 0) + 1); state.shieldWeek = wk; }
  const end = parseDay(day);
  if (!state.last || !state.streak) { state.streak = 1; }
  else if (!isWeekday(end)) return; // weekend visits earn XP but don't move the streak
  else {
    let missed = 0;
    const cur = parseDay(state.last);
    cur.setDate(cur.getDate() + 1);
    while (cur < end) { if (isWeekday(cur)) missed++; cur.setDate(cur.getDate() + 1); }
    if (missed <= state.shields) { state.shields -= missed; state.streak += 1; }
    else state.streak = 1;
  }
  state.best = Math.max(state.best, state.streak);
}

export function checkIn(today) {
  const d = todayStr();
  if (state.last === d) return;
  updateStreak(d);
  state.checkins = [...state.checkins, d].slice(-400);
  state.last = d;
  award(XP.checkin, "Daily check-in");
  if (today?.status === "none") {
    state.quietDays.push(d);
    award(XP.quiet, "Patience: no setups, no forced trades");
  }
  checkQuests();
  save();
}

export function reviewPick(id, ticker) {
  if (state.reviewed[id]) return;
  state.reviewed[id] = todayStr();
  award(XP.review, `Reviewed ${ticker}`);
  checkQuests(); save();
}

export function ruleCheck(id, ticker, answers) {
  if (state.ruleChecks[id]) return;
  state.ruleChecks[id] = { d: todayStr(), answers };
  award(XP.rules, `Followed the plan on ${ticker}`);
  checkQuests(); save();
}

export function healthRead(week) {
  if (state.healthWeeks.includes(week)) return;
  state.healthWeeks.push(week);
  award(XP.health, "Read the weekly System Health report");
  checkQuests(); save();
}

export function setFlag(name) {
  if (state.flags[name]) return;
  state.flags[name] = todayStr();
  checkQuests(); save();
}

export function reset() { state = blank(); save(); }

// ---------------------------------------------------------------------------
export function toast(title, sub) {
  const box = document.getElementById("toasts");
  if (!box) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.innerHTML = `${esc(title)}${sub ? `<small>${esc(sub)}</small>` : ""}`;
  box.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

export function renderPlayer(el) {
  const L = level();
  el.innerHTML = `<span class="lvl" title="${esc(L.title)}">Lv ${L.level}</span>`
    + `<span class="xpbar" title="${L.into} / ${L.span} XP to next level"><i style="width:${(L.into / L.span) * 100}%"></i></span>`
    + `<span class="xptext">${state.xp} XP</span>`
    + `<span class="streak" title="Weekday check-in streak">${ICONS.flame}${state.streak}</span>`;
}

export function renderQuests(view) {
  const L = level();
  view.innerHTML = `
  <div class="stack">
    <div class="panel hero">
      <div class="spread">
        <div>
          <div class="muted small">Level ${L.level}</div>
          <div class="big">${esc(L.title)}</div>
          <p>${state.xp} XP total · ${L.span - L.into} XP to level ${L.level + 1}</p>
        </div>
        <div class="tiles" style="min-width:260px">
          <div class="tile"><div class="label">Streak</div><div class="value">${state.streak}</div><div class="sub">best ${state.best}</div></div>
          <div class="tile"><div class="label">Shields</div><div class="value">${state.shields}</div><div class="sub">cover a missed day</div></div>
        </div>
      </div>
      <div class="xpbar" style="width:100%;margin-top:12px"><i style="width:${(L.into / L.span) * 100}%"></i></div>
    </div>

    <div class="panel">
      <h3>How you earn XP</h3>
      <p class="muted small" style="margin:4px 0 10px">Discipline is the game. You never earn XP for trading more.</p>
      <table><tbody>
        <tr><td>Daily check-in</td><td class="num">+${XP.checkin}</td></tr>
        <tr><td>Checking in on a "No setups" day (patience)</td><td class="num">+${XP.quiet}</td></tr>
        <tr><td>Reviewing a pick card</td><td class="num">+${XP.review}</td></tr>
        <tr><td>Rule check on a pick (passing on purpose counts)</td><td class="num">+${XP.rules}</td></tr>
        <tr><td>Reading the weekly System Health report</td><td class="num">+${XP.health}</td></tr>
      </tbody></table>
    </div>

    <div class="section-title"><h2>Quests</h2><p class="muted small">${state.quests.length}/${QUESTS.length} complete</p></div>
    <div class="grid">
      ${QUESTS.map((q) => {
        const v = Math.min(q.goal, q.value(state)), done = state.quests.includes(q.id);
        return `<div class="panel quest ${done ? "complete" : ""}">
          <div class="badge">${ICONS.star}</div>
          <div><strong>${esc(q.title)}</strong><div class="muted small">${esc(q.desc)}</div>
            <div class="progress"><i style="width:${(v / q.goal) * 100}%"></i></div></div>
          <div class="small ${done ? "pos" : "muted"}">${done ? "Done" : `${v}/${q.goal}`}<br>+${q.xp}</div>
        </div>`;
      }).join("")}
    </div>

    <div class="panel">
      <h3>Recent XP</h3>
      ${state.log.length ? `<table><tbody>${state.log.slice(0, 12).map((e) =>
        `<tr><td class="muted">${esc(shortDate(e.d))}</td><td>${esc(e.why)}</td><td class="num pos">+${e.points}</td></tr>`).join("")}</tbody></table>`
        : '<p class="muted small">Nothing yet.</p>'}
      <p class="muted small" style="margin-top:12px">Progress is saved only in this browser.
        <button class="btn" id="reset-game" style="margin-left:8px">Reset progress</button></p>
    </div>
  </div>`;
  view.querySelector("#reset-game").addEventListener("click", () => {
    if (confirm("Reset all XP, streaks and quests in this browser?")) { reset(); renderQuests(view); }
  });
}
