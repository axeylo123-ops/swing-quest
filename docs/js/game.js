// Light game layer: XP, level and weekday streak, shown in the top bar.
// Earned by showing up and reviewing ideas, never by trading more. Browser-only.
import { storage, todayStr, parseDay, isWeekday, weekKey, esc } from "./util.js";
import * as fx from "./fx.js";

const KEY = "sq.game.v1";
export const XP = { checkin: 10, review: 5, holdings: 10 };
const TITLES = ["Recruit", "Operator", "Analyst", "Strategist", "Specialist", "Veteran", "Elite", "Legend"];

const blank = () => ({ xp: 0, checkins: [], reviewed: {}, streak: 0, best: 0, shields: 1, shieldWeek: null, last: null, log: [], flags: {} });
let state = { ...blank(), ...storage.get(KEY, {}) };
const listeners = [];
export const onChange = (fn) => listeners.push(fn);
export const get = () => state;
function save() { storage.set(KEY, state); listeners.forEach((fn) => fn(state)); }

const needFor = (L) => 50 * L * (L - 1);
export function level(xp = state.xp) {
  let L = 1;
  while (xp >= needFor(L + 1)) L++;
  return { level: L, title: TITLES[Math.min(L - 1, TITLES.length - 1)], into: xp - needFor(L), span: needFor(L + 1) - needFor(L) };
}

function award(points, why, origin) {
  const before = level().level;
  state.xp += points;
  state.log = [{ d: todayStr(), points, why }, ...state.log].slice(0, 40);
  if (origin) { fx.sparks(origin); fx.floatText(origin, `+${points} XP`); }
  else toast(`+${points} XP`, why);
  const after = level();
  if (after.level > before) setTimeout(() => fx.levelUp(after.level, after.title), 600);
}

function updateStreak(day) {
  const wk = weekKey(day);
  if (state.shieldWeek !== wk) { state.shields = Math.min(2, (state.shields ?? 0) + 1); state.shieldWeek = wk; }
  const end = parseDay(day);
  if (!state.last || !state.streak) { state.streak = 1; }
  else if (!isWeekday(end)) return;
  else {
    let missed = 0;
    const cur = parseDay(state.last);
    cur.setDate(cur.getDate() + 1);
    while (cur < end) { if (isWeekday(cur)) missed++; cur.setDate(cur.getDate() + 1); }
    if (missed <= state.shields) { state.shields -= missed; state.streak += 1; } else state.streak = 1;
  }
  state.best = Math.max(state.best, state.streak);
}

export function checkIn() {
  const d = todayStr();
  if (state.last === d) return;
  updateStreak(d);
  state.checkins = [...state.checkins, d].slice(-400);
  state.last = d;
  award(XP.checkin, "Daily check-in");
  save();
}

// Opening the dossier of one of today's top ideas counts as reviewing it.
export function reviewIdea(id, ticker, origin) {
  if (state.reviewed[id]) return;
  state.reviewed[id] = todayStr();
  award(XP.review, `Reviewed ${ticker}`, origin);
  save();
}

export function setFlag(name) {
  if (state.flags[name]) return;
  state.flags[name] = todayStr();
  award(XP.holdings, "Linked your holdings");
  save();
}

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
  el.innerHTML = `<span class="lvl" title="${esc(L.title)}">LV ${L.level}</span>
    <span class="bar" title="${L.into}/${L.span} XP to level ${L.level + 1}"><i style="width:${(L.into / L.span) * 100}%"></i></span>
    <span title="Weekday check-in streak">${state.streak}D STREAK</span>`;
}
