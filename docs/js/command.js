// Command: the first screen. Top ideas, your holdings, the watchlist.
import { esc, niceDate, shortDate, addTradingDays, storage } from "./util.js";
import { gauge, meters, chip, pct, cls, money, headlineUpside, zoneBar } from "./ui.js";
import * as fx from "./fx.js";

const HOLDINGS_KEY = "sq.portfolio.v1";

function ideaCard(s, i, asOf) {
  const up = headlineUpside(s), pl = s.plan || {};
  const exitBy = pl.time_stop_days ? shortDate(addTradingDays(addTradingDays(asOf, 1), pl.time_stop_days - 1)) : "–";
  const lead = s.note?.upside?.split(" · ")[0] || "";
  return `<article class="hud hot idea reveal ${i === 0 ? "lead" : ""}" tabindex="0" data-open="${esc(s.ticker)}" aria-label="Open ${esc(s.ticker)} dossier">
    <div class="in">
      <div class="idea-top">
        <span class="rankbadge">#${i + 1}</span>
        <div style="min-width:0"><div class="ticker">${esc(s.ticker)}</div><div class="company">${esc(s.name || "")}</div></div>
        ${gauge(s.conviction)}
      </div>
      <div class="spread">
        <div class="bignum ${cls(up.value)}" data-count="${up.value ?? ""}">${pct(up.value)}<small>${esc(up.label)}</small></div>
        ${chip(s.verdict)}
      </div>
      <div class="kv">
        <div><div class="k">Buy zone</div><div class="v">${pl.entry_low?.toFixed(2) ?? "–"}–${pl.entry_high?.toFixed(2) ?? "–"}</div></div>
        <div><div class="k">Stop</div><div class="v down">${pl.stop?.toFixed(2) ?? "–"}</div></div>
        <div><div class="k">Target</div><div class="v up">${pl.target?.toFixed(2) ?? "–"}</div></div>
        <div><div class="k">Exit by</div><div class="v">${esc(exitBy)}</div></div>
      </div>
      ${zoneBar(s)}
      ${meters(s.pillars)}
      <div class="why">${esc(lead)}</div>
      <div class="spread">${s.next_earnings ? `<span class="tiny muted">Next earnings ${esc(shortDate(s.next_earnings))}</span>` : "<span></span>"}
        <button class="paper-btn" data-buy="${esc(s.ticker)}" aria-label="Paper buy ${esc(s.ticker)}">＋ Paper $100</button></div>
    </div></article>`;
}

// High-upside lane: +50% analyst potential with 2+ catalysts. Bigger swings, so a wider stop and a 30-day limit.
function highLane(ready, waiting) {
  if (!ready.length && !waiting.length) return "";
  const row = (s) => `<div class="hu-row" data-open="${esc(s.ticker)}" tabindex="0" role="button" aria-label="Open ${esc(s.ticker)} dossier">
      <div class="hu-pot num up">${pct(s.potential)}<small>analyst target</small></div>
      <div style="min-width:0"><div><b>${esc(s.ticker)}</b> <span class="muted tiny">${esc((s.name || "").slice(0, 30))}</span></div>
        <div class="hu-cats">${(s.catalysts || []).map((c) => `<span class="cat">${esc(c)}</span>`).join("")}</div>
        <div class="tiny t2">${s.hu_ready
          ? `Buy ${s.plan.entry_low.toFixed(2)}–${s.plan.entry_high.toFixed(2)} · stop ${s.plan.stop.toFixed(2)} · target ${s.plan.target.toFixed(2)} · ${s.plan.time_stop_days}-day limit`
          : esc(s.why)}${s.next_earnings ? ` · earnings ${esc(shortDate(s.next_earnings))}` : ""}</div></div>
      <div style="display:grid;gap:6px;justify-items:end">${chip(s.hu_ready ? "High-upside" : "Watch")}
        <button class="paper-btn" data-buy="${esc(s.ticker)}" aria-label="Paper buy ${esc(s.ticker)}">＋ Paper</button></div>
    </div>`;
  return `<div class="hud hu"><div class="in">
    <div class="section-head"><h2>High-upside lane</h2><span class="tiny warn">higher risk · size these smaller</span></div>
    <p class="tiny t2" style="margin:0 0 10px">Stocks analysts see rising 50%+ that also have two separate catalysts. Big targets come with big swings: wider stops, 30-day time limit.</p>
    ${ready.length ? ready.map(row).join("") : `<div class="notice" style="margin-bottom:10px">None ready to buy today. These qualify but their charts are still falling: wait for them to turn up.</div>`}
    ${waiting.length ? `${ready.length ? `<h3 style="margin:12px 0 6px">Waiting for the chart to turn</h3>` : ""}${waiting.map(row).join("")}` : ""}
  </div></div>`;
}

// What changed since the last trading day, with your holdings first.
function changesStrip(ch, universe) {
  if (!ch) return "";
  const mine = new Set((storage.get(HOLDINGS_KEY, null)?.holdings || []).map((h) => h.symbol));
  const v = Object.entries(ch.verdicts || {});
  const yours = v.filter(([t, x]) => mine.has(t) && x.hold_was !== x.hold_now);
  const link = (t) => `<button class="tk-link" data-open="${esc(t)}">${esc(t)}</button>`;
  const parts = [];
  if (yours.length) parts.push(`<span class="warn">Your holdings:</span> ${yours.map(([t, x]) => `${link(t)} ${esc(x.hold_was || "–")} → <b>${esc(x.hold_now)}</b>`).join(", ")}`);
  if (ch.new_ideas?.length) parts.push(`<span class="neon">New:</span> ${ch.new_ideas.map((x) => link(x.ticker)).join(" ")}`);
  if (ch.dropped?.length) parts.push(`<span class="muted">Dropped:</span> ${ch.dropped.map((x) => `${link(x.ticker)} <span class="tiny muted">(${esc(x.now)})</span>`).join(" ")}`);
  const upgrades = v.filter(([, x]) => x.now === "Buy candidate" && x.was !== "Buy candidate").length;
  parts.push(`<span class="muted">${v.length} verdict changes · ${upgrades} new buy candidates</span>`);
  return `<div class="changes"><span class="ch-k">Since ${esc(shortDate(ch.since))}</span>${parts.map((p) => `<span class="ch-part">${p}</span>`).join("")}</div>`;
}

function holdingsPanel(universe) {
  const saved = storage.get(HOLDINGS_KEY, null);
  const holdings = saved?.holdings || [];
  if (!holdings.length) {
    return `<div class="hud"><div class="in"><div class="section-head"><h2>Your holdings</h2></div>
      <p class="small t2" style="margin:0 0 12px">Import your Questrade file once and every holding gets a verdict here: add, hold, trim or review. It stays in this browser.</p>
      <a class="btn" href="#holdings">Link holdings</a></div></div>`;
  }
  const by = Object.fromEntries((universe?.stocks || []).map((s) => [s.ticker, s]));
  const order = { Review: 0, "Trim?": 1, Add: 2, Hold: 3 };
  const rows = holdings.map((h) => ({ h, s: by[h.symbol] })).sort((a, b) =>
    (a.s ? order[a.s.hold] ?? 4 : 5) - (b.s ? order[b.s.hold] ?? 4 : 5));
  return `<div class="hud"><div class="in"><div class="section-head"><h2>Your holdings</h2><a class="tiny" href="#holdings">manage</a></div>
    ${rows.map(({ h, s }) => `<div class="hold-row" ${s ? `data-open="${esc(s.ticker)}"` : ""}>
      <span><span class="tk">${esc(h.symbol)}</span> <span class="muted tiny">${s ? `#${s.rank} · conv ${Math.round(s.conviction)}` : ""}</span></span>
      ${s ? chip(s.hold) : '<span class="chip ca">not covered</span>'}
      <span class="reason">${s ? esc(s.hold_why) : "Not in the ranked universe (too small, thinly traded, or not a stock we cover)."}</span>
    </div>`).join("")}</div></div>`;
}

function watchTable(list) {
  if (!list.length) return "";
  return `<div class="hud"><div class="in">
    <div class="section-head"><h2>Watchlist</h2><span class="tiny muted">next best by conviction · tap for the dossier</span></div>
    <div class="table-wrap"><table class="wl"><thead><tr><th>#</th><th>Stock</th><th class="num">Conv</th><th class="num">Upside</th><th>Status</th><th>Why</th></tr></thead>
    <tbody>${list.map((s) => {
      const up = headlineUpside(s);
      return `<tr data-open="${esc(s.ticker)}" tabindex="0"><td class="num muted">${s.rank}</td>
        <td><b>${esc(s.ticker)}</b> <span class="muted tiny">${esc((s.name || "").slice(0, 26))}</span></td>
        <td class="num neon">${Math.round(s.conviction)}</td><td class="num ${cls(up.value)}">${pct(up.value)}</td>
        <td>${chip(s.verdict)}</td><td class="tiny t2" style="white-space:normal;min-width:180px">${esc(s.why)}</td></tr>`;
    }).join("")}</tbody></table></div></div></div>`;
}

export function renderCommand(view, board, universe, open, changes) {
  if (!board) {
    view.innerHTML = `<div class="notice warn">No board yet. Run <code>python -m swingquest rank</code>.</div>`;
    return;
  }
  const top = board.top || [];
  view.innerHTML = `
  <div class="stack">
    <div class="spread">
      <div><h1 style="font-size:26px;letter-spacing:.12em">Today's top ideas</h1>
        <div class="small muted">Scan of ${board.ranked_n.toLocaleString()} stocks · prices as of ${esc(niceDate(board.as_of))} · ranked on ${Object.keys(board.weights).length} pillars</div></div>
    </div>
    ${changesStrip(changes, universe)}
    ${top.length ? `<div class="ideas">${top.map((s, i) => ideaCard(s, i, board.as_of)).join("")}</div>`
      : `<div class="notice">No stock passes every check tonight (upside, quality, risk and timing). The best candidates are on the watchlist below.</div>`}
    ${highLane(board.high || [], board.high_wait || [])}
    <div class="grid-main">
      <div class="stack">${watchTable(board.watch || [])}</div>
      <div class="stack">${holdingsPanel(universe)}</div>
    </div>
  </div>`;
  view.querySelectorAll("[data-count]").forEach((el) => {
    const v = parseFloat(el.dataset.count);
    if (Number.isFinite(v)) {
      const small = el.querySelector("small").outerHTML;
      fx.countUp({ set textContent(t) { el.innerHTML = t + small; } }, v, (x) => pct(x));
    }
  });
  view.querySelectorAll("[data-open]").forEach((el) => {
    el.addEventListener("click", () => open(el.dataset.open, el));
    el.addEventListener("keydown", (e) => { if (e.target === el && (e.key === "Enter" || e.key === " ") && el.tagName !== "BUTTON") { e.preventDefault(); open(el.dataset.open, el); } });
  });
  view.querySelectorAll("[data-buy]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    open(b.dataset.buy, b, { buy: true });
  }));
}
