// The System Health tab: which factors help, which don't, suggested weights.
// Reads data/health.json (written weekly). Until it exists, shows a preview
// built from the backtest scorecard.
import { esc, pct, niceDate, weekKey, todayStr } from "./util.js";
import { hbarChart } from "./charts.js";
import * as game from "./game.js";

const LABELS = {
  cluster: "Insider cluster", role: "Role (CEO/CFO/director)", dollar_size: "$ size", stake_increase: "Stake increase",
  first_buy: "First buy in 12 mo", price_context: "Near 52-week low",
};
const VERDICT = {
  helping: { cls: "ready", text: "Helping" }, hurting: { cls: "extended", text: "Hurting" },
  unclear: { cls: "wait", text: "Unclear" }, "not enough data": { cls: "lowdata", text: "Not enough data" },
};

// Same rule as swingquest/health.py: a factor "helps" if signals that earned
// points beat those that didn't by at least 0.5% over 15 days (vs SPY).
function previewFromScorecard(card, weights) {
  const factors = Object.entries(card.by_factor).map(([name, f]) => {
    let verdict = "unclear";
    if (!f.enough_data || f.edge_excess_15 == null) verdict = "not enough data";
    else if (f.edge_excess_15 >= 0.005) verdict = "helping";
    else if (f.edge_excess_15 <= -0.005) verdict = "hurting";
    return { name, label: LABELS[name] || name, weight: weights?.[name], edge: f.edge_excess_15,
      with_n: f.with.n, without_n: f.without.n, verdict };
  });
  return { preview: true, generated_at: null, week: null, factors, suggestions: [], observations: [], improvements: [] };
}

export function renderHealth(view, health, scorecard, today) {
  if (!health && scorecard?.backtest) health = previewFromScorecard(scorecard.backtest, today?.rules?.weights);
  if (!health) {
    view.innerHTML = `<div class="panel empty"><div class="big">No health report yet</div><p>It appears after the first backtest.</p></div>`;
    return;
  }
  const week = health.week || weekKey(todayStr());
  const read = game.get().healthWeeks.includes(week);
  const groups = { helping: [], hurting: [], unclear: [], "not enough data": [] };
  health.factors.forEach((f) => groups[f.verdict]?.push(f));

  view.innerHTML = `<div class="stack">
    <div class="panel hero">
      <div class="spread">
        <div><div class="muted small">${health.preview ? "Preview from the backtest" : `Week of ${esc(niceDate(week))}`}</div>
          <div class="big">System Health</div>
          <p>Which parts of the score actually predict better results, and what to improve.</p></div>
        <button class="btn ${read ? "done" : "primary"}" id="health-read" ${read ? "disabled" : ""}>${read ? "Read this week" : `Mark as read · +${game.XP.health} XP`}</button>
      </div>
    </div>

    <div class="grid">
      ${["helping", "hurting", "unclear", "not enough data"].map((v) => `
        <div class="panel"><div class="row" style="margin-bottom:8px"><span class="chip ${VERDICT[v].cls}">${VERDICT[v].text}</span>
          <span class="muted small">${groups[v].length} factor${groups[v].length === 1 ? "" : "s"}</span></div>
          ${groups[v].length ? `<ul class="reasons ${v === "helping" ? "" : "notes"}">${groups[v].map((f) =>
            `<li>${esc(f.label)} <span class="muted small">(${pct(f.edge)} edge, ${f.with_n} strong / ${f.without_n} weak)</span></li>`).join("")}</ul>`
            : '<p class="muted small" style="margin:0">None</p>'}</div>`).join("")}
    </div>

    <div class="panel">
      <h3>Factor edge</h3>
      <p class="muted small" style="margin:2px 0 8px">How much better (or worse) signals did over 15 days vs SPY when the factor was
        strong (earned at least half its points) compared with weak. * = not enough data (under 30 on one side).</p>
      <div class="chart" id="edge-chart"></div>
    </div>

    <div class="panel">
      <h3>Suggested weight changes</h3>
      ${health.suggestions?.length ? `<div class="table-wrap"><table>
        <thead><tr><th>Factor</th><th class="num">Now</th><th class="num">Suggested</th><th>Why</th></tr></thead>
        <tbody>${health.suggestions.map((s) => `<tr><td>${esc(LABELS[s.factor] || s.factor)}</td><td class="num">${s.current}</td>
          <td class="num"><strong>${s.suggested}</strong></td><td class="muted">${esc(s.why)}</td></tr>`).join("")}</tbody></table></div>
        <p class="muted small">Nothing changes automatically. If you agree, copy the numbers from
          <code>config/weights_proposed.yaml</code> into <code>config/weights.yaml</code>.</p>`
        : `<p class="muted small" style="margin:0">${health.preview ? "Suggestions arrive with the weekly report." : "No changes suggested this week."}</p>`}
    </div>

    ${health.observations?.length || health.improvements?.length ? `<div class="grid">
      <div class="panel"><h3>What we noticed</h3><ul class="reasons notes">${(health.observations || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul></div>
      <div class="panel"><h3>Where to improve</h3><ul class="reasons cautions">${(health.improvements || []).map((o) => `<li>${esc(o)}</li>`).join("")}</ul></div>
    </div>` : ""}
  </div>`;

  hbarChart(view.querySelector("#edge-chart"), health.factors.map((f) => ({
    label: f.label, value: f.edge, lowData: f.verdict === "not enough data",
    tip: `<strong>${esc(f.label)}</strong><br>Edge ${pct(f.edge)}<br>${f.with_n} strong, ${f.without_n} weak`,
  })));
  view.querySelector("#health-read").addEventListener("click", () => { game.healthRead(week); renderHealth(view, health, scorecard, today); });
}
