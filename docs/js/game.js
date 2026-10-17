// The game layer: XP, levels, streaks, badges. Stored only in this browser.
// XP rewards good habits (checking in, reviewing, keeping your vows),
// never the number of trades.
import { storage, todayStr, parseDay, isWeekday, weekKey, esc, shortDate } from "./util.js";
import { crest, emblem, torch, flourish } from "./art.js";
import * as fx from "./fx.js";

const KEY = "sq.game.v1";
export const XP = { checkin: 10, quiet: 5, review: 5, rules: 15, health: 25 };
const TITLES = ["Rookie Scout", "Chart Apprentice", "Insider Tracker", "Patient Hunter",
  "Swing Ranger", "Signal Sage", "Market Monk", "Quest Master"];

// Badges. Add new ones by adding an entry; `value` reads progress from the saved state.
export const QUESTS = [
  { id: "first-steps", title: "First Steps", emblem: "boot", desc: "Visit the Quest Board for the first time", goal: 1, xp: 20, value: (s) => s.checkins.length },
  { id: "week-warrior", title: "Week Warrior", emblem: "flame", desc: "Keep a 5-day check-in streak", goal: 5, xp: 50, value: (s) => s.best },
  { id: "month-discipline", title: "Iron Discipline", emblem: "crown", desc: "Keep a 20-day check-in streak", goal: 20, xp: 200, value: (s) => s.best },
  { id: "careful-reader", title: "Careful Reader", emblem: "scroll", desc: "Seal 10 quest scrolls as reviewed", goal: 10, xp: 50, value: (s) => Object.keys(s.reviewed).length },
  { id: "rule-keeper", title: "Oathkeeper", emblem: "oath", desc: "Swear the Trader's Oath 5 times (passing counts)", goal: 5, xp: 75, value: (s) => Object.keys(s.ruleChecks).length },
  { id: "patience", title: "The Patient", emblem: "hourglass", desc: "Visit on 5 empty-board nights without forcing a trade", goal: 5, xp: 50, value: (s) => s.quietDays.length },
  { id: "health-inspector", title: "Shadow Slayer", emblem: "eye", desc: "Win 4 weekly Reckonings", goal: 4, xp: 100, value: (s) => s.healthWeeks.length },
  { id: "know-holdings", title: "Keeper of Keys", emblem: "key", desc: "Bring your portfolio to the Treasury", goal: 1, xp: 20, value: (s) => (s.flags.portfolio ? 1 : 0) },
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

function award(points, why, origin) {
  const before = level().level;
  state.xp += points;
  state.log.unshift({ d: todayStr(), points, why });
  state.log = state.log.slice(0, 40);
  toast(`+${points} XP`, why);
  if (origin) { fx.sparks(origin); fx.floatText(origin, `+${points} XP`); }
  const after = level();
  if (after.level > before) setTimeout(() => fx.levelUp(after.level, after.title), origin ? 900 : 300);
}

function checkQuests(origin) {
  for (const q of QUESTS) {
    if (!state.quests.includes(q.id) && q.value(state) >= q.goal) {
      state.quests.push(q.id);
      award(q.xp, `Badge earned: ${q.title}`, origin);
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
    award(XP.quiet, "Patience: an empty board, no forced trades");
  }
  checkQuests();
  save();
}

export function reviewPick(id, ticker, origin) {
  if (state.reviewed[id]) return;
  state.reviewed[id] = todayStr();
  award(XP.review, `Sealed the ${ticker} scroll`, origin);
  checkQuests(origin); save();
}

export function ruleCheck(id, ticker, answers, origin) {
  if (state.ruleChecks[id]) return;
  state.ruleChecks[id] = { d: todayStr(), answers };
  award(XP.rules, answers.passed ? `Wisely passed on ${ticker}` : `Swore the oath on ${ticker}`, origin);
  checkQuests(origin); save();
}

export function healthRead(week, origin) {
  if (state.healthWeeks.includes(week)) return;
  state.healthWeeks.push(week);
  award(XP.health, "Won the weekly Reckoning", origin);
  checkQuests(origin); save();
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
  setTimeout(() => t.remove(), 3300);
}

export function renderPlayer(el) {
  const L = level();
  el.innerHTML = `${crest(L.level, 34)}
    <div class="who"><b>${esc(L.title)}</b><span>${state.xp} XP</span>
      <div class="xpbar" title="${L.into} / ${L.span} XP to level ${L.level + 1}"><i style="width:${(L.into / L.span) * 100}%"></i></div></div>
    <span class="streak" title="Weekday check-in streak">${torch(16)}${state.streak}</span>`;
}

export function renderHero(view) {
  const L = level();
  view.innerHTML = `
  <div class="stack">
    <div class="panel framed">
      <div class="hero-sheet">
        ${crest(L.level, 120)}
        <div>
          <div class="muted small" style="font-family:var(--font-display);letter-spacing:.2em">LEVEL ${L.level}</div>
          <div class="display" style="font-size:32px;color:var(--gold-bright)">${esc(L.title)}</div>
          <div class="xpbar" style="margin:10px 0 4px"><i style="width:${(L.into / L.span) * 100}%"></i></div>
          <div class="muted small">${state.xp} XP · ${L.span - L.into} XP until level ${L.level + 1}</div>
          <div class="tallies" style="margin-top:12px">
            <div class="tally"><div class="v">${torch(18)} ${state.streak}</div><div class="k">Streak</div><div class="s">best ${state.best}</div></div>
            <div class="tally"><div class="v">${state.shields}</div><div class="k">Shields</div><div class="s">each covers a missed day</div></div>
            <div class="tally"><div class="v">${state.quests.length}/${QUESTS.length}</div><div class="k">Badges</div><div class="s">earned</div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="section-title"><h2>Badges</h2>${flourish()}<p>Earned by habits, never by trading more.</p></div>
    <div class="badges">${QUESTS.map((q) => {
      const v = Math.min(q.goal, q.value(state)), done = state.quests.includes(q.id);
      return `<div class="badge ${done ? "earned" : ""}" title="${esc(q.desc)}">
        <div class="medal">${emblem(q.emblem)}</div>
        <div class="bname">${esc(q.title)}</div><div class="bdesc">${esc(q.desc)}</div>
        ${done ? `<div class="small" style="color:var(--gold);margin-top:6px">Earned · +${q.xp} XP</div>`
               : `<div class="meter"><i style="width:${(v / q.goal) * 100}%"></i></div><div class="small muted">${v}/${q.goal} · +${q.xp} XP</div>`}
      </div>`;
    }).join("")}</div>

    <div class="grid">
      <div class="panel on-dark"><h3>How heroes earn XP</h3>
        <table style="margin-top:6px"><tbody>
          <tr><td>Daily visit to the Quest Board</td><td class="num">+${XP.checkin}</td></tr>
          <tr><td>Visiting on an empty-board night (patience)</td><td class="num">+${XP.quiet}</td></tr>
          <tr><td>Sealing a quest scroll as reviewed</td><td class="num">+${XP.review}</td></tr>
          <tr><td>Swearing the Trader's Oath (passing counts)</td><td class="num">+${XP.rules}</td></tr>
          <tr><td>Winning the weekly Reckoning</td><td class="num">+${XP.health}</td></tr>
        </tbody></table></div>
      <div class="panel on-dark"><h3>The chronicle of deeds</h3>
        ${state.log.length ? `<table style="margin-top:6px"><tbody>${state.log.slice(0, 10).map((e) =>
          `<tr><td class="muted">${esc(shortDate(e.d))}</td><td>${esc(e.why)}</td><td class="num pos">+${e.points}</td></tr>`).join("")}</tbody></table>`
          : '<p class="muted small">No deeds yet.</p>'}
        <p class="muted small" style="margin-top:12px">Saved only in this browser.
          <button class="btn" id="reset-game" style="margin-left:6px;padding:6px 10px">Reset</button></p>
      </div>
    </div>
  </div>`;
  view.querySelector("#reset-game").addEventListener("click", () => {
    if (confirm("Reset all XP, streaks and badges in this browser?")) { reset(); renderHero(view); }
  });
}
