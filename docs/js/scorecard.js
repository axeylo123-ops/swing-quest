// The Scorecard tab: honest backtest + live results.
import { esc, pct, rate, niceDate, signClass } from "./util.js";
import { barChart, splitBar } from "./charts.js";

const STATUS_NAMES = { pick: "Picks (score ≥ min + Ready)", watch: "Watchlist (good score, timing not Ready)", below: "Below min score" };

const lowChip = (s) => (s && !s.enough_data ? ' <span class="chip lowdata">not enough data</span>' : "");

function tiles(s) {
  return `<div class="tiles">
    <div class="tile"><div class="label">Finished picks</div><div class="value">${s.n}</div><div class="sub">${s.n_trades} trades taken</div></div>
    <div class="tile"><div class="label">Win rate</div><div class="value">${rate(s.win_rate)}</div><div class="sub">trades that made money</div></div>
    <div class="tile"><div class="label">Avg trade</div><div class="value ${signClass(s.avg_trade_return)}">${pct(s.avg_trade_return)}</div><div class="sub">${s.avg_r == null ? "" : `${s.avg_r > 0 ? "+" : ""}${s.avg_r.toFixed(2)}R per trade`}</div></div>
    <div class="tile"><div class="label">Beat SPY</div><div class="value">${rate(s.beat_spy_rate)}</div><div class="sub">over 15 days</div></div>
    <div class="tile"><div class="label">15 days vs SPY</div><div class="value ${signClass(s.avg_excess_15)}">${pct(s.avg_excess_15)}</div><div class="sub">average extra return</div></div>
  </div>`;
}

function table(groups, names = {}) {
  const rows = Object.entries(groups);
  if (!rows.length) return '<p class="muted small">No data yet.</p>';
  return `<div class="table-wrap"><table>
    <thead><tr><th>Group</th><th class="num">Signals</th><th class="num">Beat SPY</th><th class="num">15d vs SPY</th>
      <th class="num">Trades</th><th class="num">Win rate</th><th class="num">Avg trade</th><th class="num">Target first</th></tr></thead>
    <tbody>${rows.map(([k, s]) => `<tr>
      <td>${esc(names[k] || k)}${lowChip(s)}</td><td class="num">${s.n}</td><td class="num">${rate(s.beat_spy_rate)}</td>
      <td class="num ${signClass(s.avg_excess_15)}">${pct(s.avg_excess_15)}</td><td class="num">${s.n_trades}</td>
      <td class="num">${rate(s.win_rate)}</td><td class="num ${signClass(s.avg_trade_return)}">${pct(s.avg_trade_return)}</td>
      <td class="num">${rate(s.target_first)}</td></tr>`).join("")}</tbody></table></div>`;
}

function section(title, card, id) {
  const p = card.picks;
  return `
  <div class="panel stack">
    <div class="spread"><h2>${esc(title)}</h2>
      <span class="muted small">${card.start ? `${esc(niceDate(card.start))} – ${esc(niceDate(card.end))}` : ""}</span></div>
    ${card.events != null ? `<p class="muted small" style="margin:0">${card.events.toLocaleString()} insider-buying events → ${card.all_signals.n.toLocaleString()} finished signals that passed the universe rules
      (${card.open_signals} still open). ${p.enough_data ? "" : "<strong>Picks have fewer than 30 results: treat these numbers as not enough data.</strong>"}</p>` : ""}
    <h3>Picks${lowChip(p)}</h3>
    ${tiles(p)}
    <div>
      <div class="muted small">How pick trades ended</div>
      <div data-split="${id}"></div>
    </div>
    <div>
      <h3>Do higher scores do better?</h3>
      <p class="muted small" style="margin:2px 0 8px">Average 15-day return vs SPY for every signal, grouped by score. Faded bars = fewer than 30 signals.</p>
      <div class="chart" data-buckets="${id}"></div>
    </div>
    <div>
      <h3>Picks by month</h3>
      <p class="muted small" style="margin:2px 0 8px">Average trade return of the picks made each month.</p>
      <div class="chart" data-monthly="${id}"></div>
    </div>
    <details><summary>By signal type</summary>${table(card.by_status, STATUS_NAMES)}</details>
    <details><summary>By score</summary>${table(card.by_score_bucket)}</details>
    <details><summary>By chart timing</summary>${table(card.by_timing)}</details>
    <details><summary>By insider role</summary>${table(card.by_role)}</details>
    <details><summary>Older half vs newer half (a big gap suggests luck)</summary>${table(card.by_period)}</details>
  </div>`;
}

function draw(view, card, id) {
  const p = card.picks;
  splitBar(view.querySelector(`[data-split="${id}"]`), [
    { label: "Target hit first", value: p.target_first, color: "var(--good)" },
    { label: "Stop hit first", value: p.stop_first, color: "var(--critical)" },
    { label: "15-day time exit", value: p.time_exit, color: "var(--muted)" },
  ]);
  barChart(view.querySelector(`[data-buckets="${id}"]`), Object.entries(card.by_score_bucket).map(([k, s]) => ({
    label: k, value: s.avg_excess_15, sub: `n=${s.n}`, lowData: !s.enough_data,
    tip: `<strong>Score ${esc(k)}</strong><br>${s.n} signals${s.enough_data ? "" : " (not enough data)"}<br>15d vs SPY ${pct(s.avg_excess_15)}<br>Beat SPY ${rate(s.beat_spy_rate)}`,
  })), { format: (v) => pct(v, 1) });
  const months = card.monthly_picks || [];
  barChart(view.querySelector(`[data-monthly="${id}"]`), months.map((m) => ({
    label: m.month.slice(2).replace("-", "/"), value: m.avg_trade_return, lowData: m.n < 5,
    tip: `<strong>${esc(m.month)}</strong><br>${m.n} pick${m.n === 1 ? "" : "s"}<br>Avg trade ${pct(m.avg_trade_return)}`,
  })), { format: (v) => pct(v, 0), labelEvery: Math.max(1, Math.ceil(months.length / 8)), height: 170 });
}

export function renderScorecard(view, data) {
  if (!data?.backtest) {
    view.innerHTML = `<div class="panel empty"><div class="big">No scorecard yet</div><p>Run <code>python -m swingquest backtest</code>.</p></div>`;
    return;
  }
  view.innerHTML = `<div class="stack">
    <div class="panel hero"><div class="big">Is it working?</div>
      <p>Every past signal, replayed with only the information available at the time: buy at the next open,
      skip if it opened above the buy zone, stop counted first if both were hit the same day.</p></div>
    ${data.live ? section("Live results", data.live, "live") : `<div class="panel"><h2>Live results</h2>
      <p class="muted">Live tracking starts once the daily scan runs automatically. Each live pick will be scored here 15 trading days after it appears.</p></div>`}
    ${section("Backtest", data.backtest, "bt")}
    <div class="panel"><h3>Read this with care</h3><ul class="reasons cautions">${(data.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>
  </div>`;
  if (data.live) draw(view, data.live, "live");
  draw(view, data.backtest, "bt");
}
