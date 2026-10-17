// The Today tab: pick cards, watchlist, and why other stocks didn't qualify.
import { esc, price, pct, money, niceDate, shortDate, addTradingDays, ICONS, $$ } from "./util.js";
import { priceChart } from "./charts.js";
import * as game from "./game.js";

const TIMING = {
  Ready: { cls: "ready", icon: ICONS.check, text: "Ready" },
  Wait: { cls: "wait", icon: ICONS.pause, text: "Wait" },
  Extended: { cls: "extended", icon: ICONS.up, text: "Extended" },
};
const FACTOR_NAMES = {
  cluster: "Insider cluster", role: "Role", dollar_size: "$ size",
  stake_increase: "Stake increase", first_buy: "First buy in 12 mo", price_context: "Near 52-wk low",
};
const RULES = [
  "I only buy inside the buy zone, or I skip it",
  "I set my stop order right away",
  "I'll sell at the target, the stop, or after 15 trading days",
];

function scoreRing(score) {
  const r = 24, c = 2 * Math.PI * r, f = Math.max(0, Math.min(100, score)) / 100;
  return `<div class="score-ring" title="Score ${score} of 100">
    <svg viewBox="0 0 58 58"><circle cx="29" cy="29" r="${r}" fill="none" stroke="var(--panel-2)" stroke-width="6"/>
    <circle cx="29" cy="29" r="${r}" fill="none" stroke="url(#ring)" stroke-width="6" stroke-linecap="round"
      stroke-dasharray="${c * f} ${c}"/>
    <defs><linearGradient id="ring"><stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent-2)"/></linearGradient></defs></svg>
    <div class="num"><span>${score}<small>score</small></span></div></div>`;
}

function timingChip(label) {
  const t = TIMING[label] || TIMING.Wait;
  return `<span class="chip ${t.cls}">${t.icon}${t.text}</span>`;
}

function card(p, asOf, compact = false) {
  const g = game.get();
  const reviewed = !!g.reviewed[p.id], ruled = !!g.ruleChecks[p.id];
  const pl = p.plan;
  const entryDay = addTradingDays(asOf, 1);
  const sellBy = addTradingDays(entryDay, pl.time_stop_days - 1);
  return `
  <article class="panel card" data-id="${esc(p.id)}">
    <div class="card-head">
      ${scoreRing(p.score)}
      <div style="flex:1;min-width:0">
        <div class="row"><span class="ticker">${esc(p.ticker)}</span>${timingChip(p.timing)}</div>
        <div class="company">${esc(p.company || "")}</div>
      </div>
    </div>

    <div class="plan">
      <div><div class="k">Buy zone</div><div class="v">${price(pl.entry_low)}–${pl.entry_high.toFixed(2)}</div></div>
      <div class="stop"><div class="k">Stop</div><div class="v">${price(pl.stop)}</div></div>
      <div class="target"><div class="k">Target</div><div class="v">${price(pl.target)}</div></div>
      <div><div class="k">Sell by</div><div class="v">${esc(shortDate(sellBy))}</div></div>
    </div>
    <div class="muted small">Risk ${pct(pl.risk_pct, 1, false)} to the stop · reward-to-risk ${pl.reward_risk}:1
      (at least ${pl.reward_risk_worst}:1 even at the top of the zone)</div>

    <div>
      <h3 style="margin-bottom:6px">Why it scored ${p.score}</h3>
      <ul class="reasons">${p.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      ${p.cautions.length ? `<ul class="reasons cautions" style="margin-top:6px">${p.cautions.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
    </div>
    <div>
      <h3 style="margin-bottom:6px">Chart timing</h3>
      <ul class="reasons notes">${p.timing_notes.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    </div>

    ${compact ? "" : `<div class="chart" data-chart="${esc(p.id)}"></div>`}

    <details>
      <summary>Insider purchases (${p.insiders.length}) and score breakdown</summary>
      <div class="table-wrap"><table>
        <thead><tr><th>Insider</th><th>Role</th><th class="num">Bought</th><th class="num">Avg price</th><th>Filed</th></tr></thead>
        <tbody>${p.insiders.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.role)}</td>
          <td class="num">${money(b.value)}</td><td class="num">${price(b.avg_price)}</td><td>${esc(shortDate(b.filed_date))}</td></tr>`).join("")}</tbody>
      </table></div>
      <div class="table-wrap" style="margin-top:10px"><table>
        <thead><tr><th>Factor</th><th class="num">Points</th></tr></thead>
        <tbody>${Object.entries(p.factors).map(([k, f]) => `<tr><td>${esc(FACTOR_NAMES[k] || k)}</td><td class="num">${f.points}</td></tr>`).join("")}</tbody>
      </table></div>
    </details>

    <div class="row">
      <button class="btn ${reviewed ? "done" : "primary"}" data-review="${esc(p.id)}" data-ticker="${esc(p.ticker)}" ${reviewed ? "disabled" : ""}>
        ${reviewed ? `${ICONS.check.replace("<svg", '<svg width="16" height="16" fill="currentColor"')} Reviewed` : `Mark reviewed · +${game.XP.review} XP`}</button>
      ${compact ? "" : `<button class="btn ${ruled ? "done" : ""}" data-rules="${esc(p.id)}" ${ruled ? "disabled" : ""}>
        ${ruled ? "Rule check done" : `Rule check · +${game.XP.rules} XP`}</button>`}
    </div>
    <div class="rulebox" data-rulebox="${esc(p.id)}" hidden>
      <div class="checklist">
        ${RULES.map((r, i) => `<label><input type="checkbox" data-rule="${i}"> ${esc(r)}</label>`).join("")}
        <label><input type="checkbox" data-pass> I'm passing on this one on purpose (that counts too)</label>
      </div>
      <button class="btn primary" data-rules-save="${esc(p.id)}" data-ticker="${esc(p.ticker)}">Save rule check</button>
    </div>
  </article>`;
}

export function renderToday(view, data) {
  if (!data) {
    view.innerHTML = `<div class="panel empty"><div class="big">No scan data yet</div><p>Run <code>python -m swingquest scan</code> to create today's results.</p></div>`;
    return;
  }
  const s = data.summary;
  const none = data.status === "none";
  view.innerHTML = `
  <div class="stack">
    <div class="panel hero">
      <div class="muted small">Scan for ${esc(niceDate(data.as_of))}</div>
      <div class="big">${none ? "No setups today." : `${data.picks.length} setup${data.picks.length > 1 ? "s" : ""} today`}</div>
      <p>${none ? "Nothing passed every rule. Patience is a position: no trade is a fine trade."
                : "Each one passed the universe rules, scored at least " + data.rules.min_score + ", and the chart says Ready."}</p>
      <div class="tiles" style="margin-top:14px">
        <div class="tile"><div class="label">Insider buys</div><div class="value">${s.insider_buys_in_window}</div><div class="sub">last 30 days</div></div>
        <div class="tile"><div class="label">New this week</div><div class="value">${s.stocks_with_new_buys}</div><div class="sub">stocks checked</div></div>
        <div class="tile"><div class="label">Watchlist</div><div class="value">${s.watchlist}</div><div class="sub">good score, wait for timing</div></div>
        <div class="tile"><div class="label">Skipped</div><div class="value">${s.skipped}</div><div class="sub">failed a rule</div></div>
      </div>
    </div>

    ${data.picks.length ? `<div class="section-title"><h2>Today's setups</h2></div>
      <div class="stack">${data.picks.map((p) => card(p, data.as_of)).join("")}</div>` : ""}

    ${data.watchlist.length ? `<div class="section-title"><h2>Watchlist</h2>
      <p class="muted small">Strong insider buying, but the chart says wait. Not a buy yet.</p></div>
      <div class="grid">${data.watchlist.map((p) => card(p, data.as_of, true)).join("")}</div>` : ""}

    <div class="panel">
      <details ${none && !data.watchlist.length ? "open" : ""}>
        <summary>Why the other ${data.skipped.length} stocks didn't qualify</summary>
        <div class="table-wrap"><table><thead><tr><th>Stock</th><th>Reason</th></tr></thead>
        <tbody>${data.skipped.map((k) => `<tr><td><strong>${esc(k.ticker)}</strong></td><td class="muted">${esc(k.reason)}</td></tr>`).join("")}</tbody></table></div>
      </details>
    </div>
    <p class="muted small">Updated ${esc(new Date(data.generated_at).toLocaleString())}. Scores use weights from config/weights.yaml (min score ${data.rules.min_score}).</p>
  </div>`;

  for (const p of data.picks) {
    const el = view.querySelector(`[data-chart="${CSS.escape(p.id)}"]`);
    if (el) priceChart(el, p.chart, p.plan);
  }
  wire(view, data);
}

function wire(view, data) {
  $$("[data-review]", view).forEach((b) => b.addEventListener("click", () => {
    game.reviewPick(b.dataset.review, b.dataset.ticker);
    renderToday(view, data);
  }));
  $$("[data-rules]", view).forEach((b) => b.addEventListener("click", () => {
    const box = view.querySelector(`[data-rulebox="${CSS.escape(b.dataset.rules)}"]`);
    box.hidden = !box.hidden;
  }));
  $$("[data-rules-save]", view).forEach((b) => b.addEventListener("click", () => {
    const box = b.closest(".rulebox");
    const ticks = $$("[data-rule]", box).map((c) => c.checked);
    const passed = box.querySelector("[data-pass]").checked;
    if (!passed && !ticks.every(Boolean)) {
      game.toast("Not yet", "Tick every rule, or mark that you're passing on purpose");
      return;
    }
    game.ruleCheck(b.dataset.rulesSave, b.dataset.ticker, { rules: ticks, passed });
    renderToday(view, data);
  }));
}
