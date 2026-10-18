// Shared UI pieces for the command-center look: gauge, pillar meters, chips, formatting.
import { esc } from "./util.js";

export const PILLARS = [
  ["upside", "Upside"], ["analysts", "Analysts"], ["insiders", "Insiders"],
  ["quality", "Quality"], ["momentum", "Momentum"], ["value", "Value"],
];

export const pct = (x, d = 0) => (x == null ? "–" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
export const cls = (x) => (x == null ? "" : x >= 0 ? "up" : "down");
export function money(x, cur = "USD") {
  if (x == null) return "–";
  const s = cur === "CAD" ? "C$" : "$", a = Math.abs(x);
  if (a >= 1e12) return `${s}${(x / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `${s}${(x / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}${(x / 1e6).toFixed(1)}M`;
  return `${s}${Number(x).toFixed(2)}`;
}

// Conviction ring: neon arc with a glow.
export function gauge(value, size = 74, label = "conviction") {
  const r = 30, c = 2 * Math.PI * r, f = Math.max(0, Math.min(100, value || 0)) / 100;
  const color = value >= 65 ? "var(--neon)" : value >= 45 ? "var(--warn)" : "var(--down)";
  return `<div class="gauge" style="width:${size}px;height:${size}px" title="Conviction ${value} of 100">
    <svg viewBox="0 0 74 74"><circle cx="37" cy="37" r="${r}" fill="none" stroke="var(--line-2)" stroke-width="5" stroke-dasharray="3 2"/>
      <circle class="arc" cx="37" cy="37" r="${r}" fill="none" stroke="${color}" stroke-width="5" stroke-dasharray="${c * f} ${c}"/></svg>
    <div class="val"><span>${Math.round(value ?? 0)}<small>${esc(label)}</small></span></div></div>`;
}

// One segmented meter per pillar (10 segments, colored by strength).
export function meters(pillars) {
  return `<div class="meters">${PILLARS.map(([k, name]) => {
    const v = pillars?.[k] ?? 0, on = Math.round(v / 10), tone = v >= 65 ? "on" : v >= 45 ? "mid" : "low";
    return `<div class="meter" title="${name}: better than ${Math.round(v)}% of stocks"><span class="name">${name}</span>
      <span class="segs">${Array.from({ length: 10 }, (_, i) => `<i class="${i < on ? tone : ""}"></i>`).join("")}</span>
      <span class="n">${Math.round(v)}</span></div>`;
  }).join("")}</div>`;
}

const VERDICT_CLASS = { "Buy candidate": "buy", Neutral: "hold", Watch: "watch", "Don't chase": "chase", "Limited upside": "limited", Avoid: "avoid",
  Add: "add", Hold: "hold", "Trim?": "trim", Review: "review" };
export const chip = (text) => `<span class="chip ${VERDICT_CLASS[text] || "watch"}">${esc(text)}</span>`;

// Best upside figure to headline: analyst target if covered, else the swing target.
export function headlineUpside(s) {
  if (s.analyst_upside != null && s.n_analysts) return { value: s.analyst_upside, label: "analyst upside" };
  return { value: s.swing_upside, label: "swing target" };
}
