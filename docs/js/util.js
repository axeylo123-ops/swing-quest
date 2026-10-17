// Small shared helpers: escaping, number formats, dates, safe storage, data loading.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

export const pct = (x, digits = 1, sign = true) =>
  x == null ? "–" : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(digits)}%`;
export const rate = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const price = (x) => (x == null ? "–" : `$${Number(x).toFixed(2)}`);
export const money = (x) => {
  if (x == null) return "–";
  const a = Math.abs(x);
  if (a >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(x / 1e3).toFixed(0)}K`;
  return `$${x.toFixed(0)}`;
};
export const dollars = (x) => (x == null ? "–" : `$${Math.round(x).toLocaleString()}`);
export const signClass = (x) => (x == null ? "" : x > 0 ? "pos" : x < 0 ? "neg" : "");

// ---- dates (all local, YYYY-MM-DD) ----
export const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const todayStr = () => iso(new Date());
export const parseDay = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
export const isWeekday = (d) => d.getDay() !== 0 && d.getDay() !== 6;
export function addTradingDays(dayStr, n) {
  const d = parseDay(dayStr);
  while (n > 0) { d.setDate(d.getDate() + 1); if (isWeekday(d)) n--; }
  return iso(d);
}
export const niceDate = (s) =>
  s ? parseDay(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "–";
export const shortDate = (s) => parseDay(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
export function weekKey(dayStr) {           // Monday of that week
  const d = parseDay(dayStr);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return iso(d);
}

// ---- localStorage that never throws (private mode, blocked storage...) ----
export const storage = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
  },
  remove(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
};

export async function loadJSON(path) {
  try {
    const r = await fetch(path, { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

export const ICONS = {
  check: '<svg viewBox="0 0 24 24"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>',
  up: '<svg viewBox="0 0 24 24"><path d="M12 4 4 14h5v6h6v-6h5z"/></svg>',
  warn: '<svg viewBox="0 0 24 24"><path d="M12 2 1 21h22L12 2zm1 15h-2v-2h2v2zm0-4h-2V9h2v4z"/></svg>',
  star: '<svg viewBox="0 0 24 24"><path d="M12 3l2.6 5.6 6 .6-4.5 4 1.3 6L12 16.3 6.6 19.2l1.3-6-4.5-4 6-.6z"/></svg>',
  flame: '<svg viewBox="0 0 24 24"><path d="M13.5 1s1 3.5-1.5 6.5S9 11 9 13a3 3 0 0 0 6 0c0-1-.5-2-.5-2s3 1.5 3 5.5A6.5 6.5 0 0 1 11 23C7 23 4 20 4 16c0-6 7-8 9.5-15z"/></svg>',
  shield: '<svg viewBox="0 0 24 24"><path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5z"/></svg>',
};
