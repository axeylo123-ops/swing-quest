// Record: how the ideas have actually done. Live tracking of the board,
// plus the insider-signal backtest as background.
import { esc, niceDate } from "./util.js";
import { pct, cls, chip } from "./ui.js";

const tile = (k, v, s, c = "") => `<div class="tile"><div class="k">${k}</div><div class="v ${c}">${v}</div><div class="s">${s}</div></div>`;
const rate = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);

export function renderRecord(view, record, scorecard) {
  const live = record?.summary;
  const bt = scorecard?.backtest?.picks;
  view.innerHTML = `<div class="stack">
    <div class="section-head"><h2>Track record</h2><span class="tiny muted">every top idea is logged and graded after 15 trading days</span></div>
    <div class="hud"><div class="in">
      <h3 style="margin-bottom:10px">Live: the new ranking system</h3>
      ${live && live.n ? `<div class="tiles">
          ${tile("Finished ideas", live.n, `${record.open?.length ?? 0} still running`)}
          ${tile("Won", rate(live.win_rate), "trades that made money")}
          ${tile("Avg trade", pct(live.avg_trade_return, 1), "entry to exit", cls(live.avg_trade_return))}
          ${tile("vs market", pct(live.avg_excess_15, 1), "15 days vs SPY", cls(live.avg_excess_15))}
        </div>`
        : `<div class="notice">Live tracking started ${record?.started ? esc(niceDate(record.started)) : "today"}. Each day's top ideas are graded 15 trading days later,
            so the first results appear in about three weeks. ${record?.open?.length ? `${record.open.length} ideas are being tracked now.` : ""}</div>`}
      ${record?.high_summary?.n ? `<h3 style="margin:14px 0 10px">High-upside lane</h3><div class="tiles">
          ${tile("Finished", record.high_summary.n, record.high_summary.n < 30 ? "under 30: too early to judge" : "trades")}
          ${tile("Won", rate(record.high_summary.win_rate), "trades that made money")}
          ${tile("Avg trade", pct(record.high_summary.avg_trade_return, 1), "entry to exit", cls(record.high_summary.avg_trade_return))}
        </div>` : ""}
      ${record?.open?.length ? `<div class="table-wrap" style="margin-top:12px"><table class="data"><thead><tr><th>Idea</th><th>Lane</th><th>Posted</th><th class="num">Conv</th>
          <th class="num">Since entry</th><th>Status</th></tr></thead><tbody>${record.open.slice(0, 15).map((r) => `<tr>
          <td><b>${esc(r.ticker)}</b></td><td class="tiny">${r.kind === "high" ? '<span class="warn">high-upside</span>' : "top idea"}</td><td>${esc(r.signal_date)}</td><td class="num neon">${Math.round(r.conviction ?? 0)}</td>
          <td class="num ${cls(r.return_now)}">${pct(r.return_now, 1)}</td><td>${r.entry_date ? "running" : "starts next open"}</td></tr>`).join("")}</tbody></table></div>` : ""}
    </div></div>
    ${bt ? `<div class="hud"><div class="in">
      <h3 style="margin-bottom:10px">Background: insider-buying signal, replayed 2023–2026</h3>
      <div class="tiles">
        ${tile("Signals", bt.n, "finished trades")}
        ${tile("Won", rate(bt.win_rate), "trades that made money")}
        ${tile("Avg trade", pct(bt.avg_trade_return, 1), "entry to exit", cls(bt.avg_trade_return))}
        ${tile("vs market", pct(bt.avg_excess_15, 1), "15 days vs SPY", cls(bt.avg_excess_15))}
      </div>
      <p class="tiny muted" style="margin:10px 0 0">This tests the insider pillar on its own. Analyst and fundamental history isn't available for free,
        so the full system is proven live, above. Free price data misses some delisted companies, so these numbers are likely a bit flattering.</p>
    </div></div>` : ""}
  </div>`;
}
