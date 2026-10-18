// The dossier: a slide-in panel with everything about one stock.
import { esc, shortDate, addTradingDays, shareCount, getRules, loadJSON } from "./util.js";
import { gauge, meters, chip, pct, cls, money, headlineUpside, zoneBar } from "./ui.js";
import { priceChart } from "./charts.js";
import * as game from "./game.js";

let notesCache = null;
const LINES = [["upside", "Upside"], ["earnings", "Earnings"], ["insiders", "Insiders"], ["quality", "Quality"],
  ["momentum", "Momentum"], ["value", "Value"]];
const drawer = () => document.getElementById("drawer");
const bg = () => document.getElementById("drawer-bg");
let isOpen = false, returnTo = null, hideTimer = null, ownHistory = false;

async function notes() {
  if (!notesCache) notesCache = (await loadJSON("data/notes.json")) || {};
  return notesCache;
}

function sizing(s) {
  const pl = s.plan;
  if (!pl) return "";
  const r = shareCount(pl.reference ?? s.price, pl.stop);
  if (!r) return `<div class="tiny muted">Set your account size in Holdings to see how many shares to buy.</div>`;
  const rules = getRules();
  if (!r.shares) return `<div class="tiny muted">One share risks more than ${rules.riskPct}% of your account. Skip, or use a bigger account.</div>`;
  return `<div class="small">Size: <b class="mono">${r.shares} shares</b> (≈ ${money(r.cost, s.currency)}). Stop hit = lose ≈ ${money(r.risk, s.currency)}
    (${rules.riskPct}% of account) · target hit = gain ≈ ${money(r.shares * (pl.target - (pl.reference ?? s.price)), s.currency)}</div>`;
}

// One keyboard listener for the app's lifetime: Esc closes, Tab stays inside the panel.
document.addEventListener("keydown", (e) => {
  if (!isOpen) return;
  if (e.key === "Escape") { e.preventDefault(); close(); }
  else if (e.key === "Tab") {
    const f = [...drawer().querySelectorAll("button, a[href], summary, [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
    else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
  }
});
// The phone's back button closes the dossier instead of leaving the page.
window.addEventListener("popstate", () => { if (isOpen) { ownHistory = false; close(); } });

function setBackground(inert) {
  for (const sel of ["main", ".topbar", ".footer"]) document.querySelector(sel)?.toggleAttribute("inert", inert);
}

export function close() {
  if (!isOpen) return;
  isOpen = false;
  const d = drawer(), b = bg();
  d.classList.remove("show"); b.classList.remove("show"); d.setAttribute("aria-hidden", "true");
  setBackground(false);
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => (b.hidden = true), 250);
  if (ownHistory) { ownHistory = false; history.back(); }
  if (returnTo?.isConnected) returnTo.focus({ preventScroll: true });
}

function show(origin) {
  const d = drawer(), b = bg();
  clearTimeout(hideTimer);
  if (!isOpen) {
    returnTo = origin || document.activeElement;
    history.pushState({ dossier: true }, "");
    ownHistory = true;
  }
  isOpen = true;
  b.hidden = false;
  setBackground(true);
  requestAnimationFrame(() => { b.classList.add("show"); d.classList.add("show"); d.setAttribute("aria-hidden", "false"); });
  b.onclick = close;
}

const header = (s, universe) => `<div class="spread"><span class="tiny muted">DOSSIER · RANK #${s.rank} OF ${universe?.stocks?.length?.toLocaleString() ?? "?"}</span>
  <button class="btn" id="close-drawer" aria-label="Close dossier">← Back · Esc</button></div>`;

export async function openDossier(ticker, board, universe, origin) {
  const lists = [...(board?.top || []), ...(board?.high || []), ...(board?.high_wait || []), ...(board?.watch || [])];
  const full = lists.find((x) => x.ticker === ticker);
  const s = full || universe?.stocks?.find((x) => x.ticker === ticker);
  if (!s) return;
  const d = drawer();
  show(origin);
  // skeleton first, so the panel opens instantly even while notes load
  d.innerHTML = `<div class="drawer-in">${header(s, universe)}<div class="ticker" style="font-size:34px">${esc(s.ticker)}</div>
    <div class="skel" style="width:60%"></div><div class="skel"></div><div class="skel" style="width:80%"></div></div>`;
  d.querySelector("#close-drawer").addEventListener("click", close);
  d.querySelector("#close-drawer").focus();
  const n = s.note || (await notes())[ticker] || {};
  if (!isOpen || !d.textContent.includes(s.ticker)) return;     // closed or replaced while loading
  const up = headlineUpside(s), pl = s.plan;
  const exitBy = pl && board ? shortDate(addTradingDays(addTradingDays(board.as_of, 1), pl.time_stop_days - 1)) : null;
  d.innerHTML = `<div class="drawer-in">
    ${header(s, universe)}
    <div class="dossier-head">
      ${gauge(s.conviction, 88)}
      <div style="min-width:0"><div class="ticker" style="font-size:34px">${esc(s.ticker)}</div>
        <div class="company">${esc(n.head?.split(" · ").slice(1).join(" · ") || s.name || "")}</div>
        <div class="row" style="margin-top:6px">${chip(s.verdict)}${s.country === "CA" ? '<span class="chip ca">Canada</span>' : ""}
          <span class="tiny muted">${esc(s.why || "")}</span></div></div>
      <div class="bignum ${cls(up.value)}" style="text-align:right">${pct(up.value)}<small>${esc(up.label)}</small></div>
    </div>
    ${s.catalysts?.length ? `<div class="hu-cats"><span class="tiny warn" style="margin-right:4px">HIGH-UPSIDE · ${pct(s.potential)} analyst target ·</span>
      ${s.catalysts.map((c) => `<span class="cat">${esc(c)}</span>`).join("")}</div>` : ""}
    ${meters(s.pillars)}
    <div class="lines">
      ${LINES.filter(([k]) => n[k]).map(([k, label]) => `<div class="line"><span class="k">${label}</span><span>${esc(n[k])}</span></div>`).join("")}
      <div class="line"><span class="k">Risks</span><span class="${(s.flags || []).length ? "" : "muted"}">${esc((n.risks || s.flags || ["nothing unusual"]).join(" · "))}</span></div>
      ${s.next_earnings ? `<div class="line"><span class="k">Next earnings</span><span>${esc(shortDate(s.next_earnings))}</span></div>` : ""}
      <div class="line"><span class="k">If you own it</span><span>${chip(s.hold)} <span class="t2 small">${esc(s.hold_why || "")}</span></span></div>
    </div>
    ${pl ? `<div><h3 style="margin-bottom:8px">Trade plan</h3>
      <div class="planbox kv">
        <div><div class="k">Buy zone</div><div class="v">${pl.entry_low.toFixed(2)}–${pl.entry_high.toFixed(2)}</div></div>
        <div><div class="k">Stop</div><div class="v down">${pl.stop.toFixed(2)} <span class="tiny">(${pct(-pl.risk_pct, 1)})</span></div></div>
        <div><div class="k">Target</div><div class="v up">${pl.target.toFixed(2)} <span class="tiny">(${pct(s.swing_upside)})</span></div></div>
        <div><div class="k">Exit by</div><div class="v">${esc(exitBy || `${pl.time_stop_days} days`)}</div></div>
      </div>
      ${zoneBar(s)}
      ${pl.stop_basis ? `<div class="tiny t2" style="margin-top:6px">Stop: ${esc(pl.stop_basis)} · Target: ${esc(pl.target_basis)}
        · reward ${pl.reward_risk?.toFixed(1)}× the risk${pl.reward_risk_worst ? ` (${pl.reward_risk_worst.toFixed(1)}× if you buy at the top of the zone)` : ""}</div>` : ""}
      <div style="margin-top:8px">${sizing(s)}</div>
      <div class="tiny muted" style="margin-top:4px">${esc((s.timing_notes || []).join(" · "))}</div></div>` : ""}
    ${s.chart?.length ? `<div class="chart" id="dossier-chart"></div>` : ""}
    <div class="tiny muted">Pillars rank this stock against every stock we cover: 70 means better than 70% of them. Not financial advice.</div>
  </div>`;
  d.querySelector("#close-drawer").addEventListener("click", close);
  d.querySelector("#close-drawer").focus({ preventScroll: true });
  if (s.chart?.length) setTimeout(() => priceChart(d.querySelector("#dossier-chart"), s.chart, pl), 60);
  if ((board?.top || []).some((x) => x.ticker === ticker)) game.reviewIdea(`${ticker}-${board.as_of}`, ticker, origin);
}
