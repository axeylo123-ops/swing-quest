// The dossier: a slide-in panel with everything about one stock.
import { esc, shortDate, addTradingDays, shareCount, getRules, loadJSON } from "./util.js";
import { gauge, meters, chip, pct, cls, money, headlineUpside } from "./ui.js";
import { priceChart } from "./charts.js";
import * as game from "./game.js";

let notesCache = null;
const LINES = [["upside", "Upside"], ["earnings", "Earnings"], ["insiders", "Insiders"], ["quality", "Quality"],
  ["momentum", "Momentum"], ["value", "Value"]];

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

export async function openDossier(ticker, board, universe, origin) {
  const full = [...(board?.top || []), ...(board?.watch || [])].find((x) => x.ticker === ticker);
  const s = full || universe?.stocks?.find((x) => x.ticker === ticker);
  if (!s) return;
  const n = s.note || (await notes())[ticker] || {};
  const up = headlineUpside(s), pl = s.plan;
  const exitBy = pl && board ? shortDate(addTradingDays(addTradingDays(board.as_of, 1), pl.time_stop_days - 1)) : null;
  const drawer = document.getElementById("drawer"), bg = document.getElementById("drawer-bg");
  drawer.innerHTML = `<div class="drawer-in">
    <div class="spread"><span class="tiny muted">DOSSIER · RANK #${s.rank} OF ${universe?.stocks?.length?.toLocaleString() ?? "?"}</span>
      <button class="btn" id="close-drawer" aria-label="Close">Close · Esc</button></div>
    <div class="dossier-head">
      ${gauge(s.conviction, 88)}
      <div style="min-width:0"><div class="ticker" style="font-size:34px">${esc(s.ticker)}</div>
        <div class="company">${esc(n.head?.split(" · ").slice(1).join(" · ") || s.name || "")}</div>
        <div class="row" style="margin-top:6px">${chip(s.verdict)}${s.country === "CA" ? '<span class="chip ca">Canada</span>' : ""}
          <span class="tiny muted">${esc(s.why || "")}</span></div></div>
      <div class="bignum ${cls(up.value)}" style="text-align:right">${pct(up.value)}<small>${esc(up.label)}</small></div>
    </div>
    ${meters(s.pillars)}
    <div class="lines">
      ${LINES.filter(([k]) => n[k]).map(([k, label]) => `<div class="line"><span class="k">${label}</span><span>${esc(n[k])}</span></div>`).join("")}
      <div class="line"><span class="k">Risks</span><span class="${(s.flags || []).length ? "" : "muted"}">${esc((n.risks || s.flags || ["nothing unusual"]).join(" · "))}</span></div>
      <div class="line"><span class="k">If you own it</span><span>${chip(s.hold)} <span class="t2 small">${esc(s.hold_why || "")}</span></span></div>
    </div>
    ${pl ? `<div><h3 style="margin-bottom:8px">Trade plan</h3>
      <div class="planbox kv">
        <div><div class="k">Buy zone</div><div class="v">${pl.entry_low.toFixed(2)}–${pl.entry_high.toFixed(2)}</div></div>
        <div><div class="k">Stop</div><div class="v down">${pl.stop.toFixed(2)} <span class="tiny">(${pct(-pl.risk_pct, 1)})</span></div></div>
        <div><div class="k">Target</div><div class="v up">${pl.target.toFixed(2)} <span class="tiny">(${pct(s.swing_upside)})</span></div></div>
        <div><div class="k">Exit by</div><div class="v">${esc(exitBy || "15 days")}</div></div>
      </div>
      <div style="margin-top:8px">${sizing(s)}</div>
      <div class="tiny muted" style="margin-top:4px">${esc((s.timing_notes || []).join(" · "))}</div></div>` : ""}
    ${s.chart?.length ? `<div class="chart" id="dossier-chart"></div>` : ""}
    <div class="tiny muted">Pillars rank this stock against every stock we cover: 70 means better than 70% of them. Not financial advice.</div>
  </div>`;
  bg.hidden = false;
  requestAnimationFrame(() => { bg.classList.add("show"); drawer.classList.add("show"); drawer.setAttribute("aria-hidden", "false"); });
  if (s.chart?.length) setTimeout(() => priceChart(drawer.querySelector("#dossier-chart"), s.chart, pl), 60);
  const close = () => { drawer.classList.remove("show"); bg.classList.remove("show"); drawer.setAttribute("aria-hidden", "true"); setTimeout(() => (bg.hidden = true), 250); };
  drawer.querySelector("#close-drawer").addEventListener("click", close);
  bg.onclick = close;
  document.addEventListener("keydown", function esc_(e) { if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc_); } });
  drawer.querySelector("#close-drawer").focus();
  if ((board?.top || []).some((x) => x.ticker === ticker)) game.reviewIdea(`${ticker}-${board.as_of}`, ticker, origin);
}
