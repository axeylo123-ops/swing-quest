// System: how the ranking works, its weights and rules, in plain words.
import { esc } from "./util.js";
import { PILLARS } from "./ui.js";

const WHAT = {
  upside: "Analyst average target vs today's price (65%) and room back to the 52-week high (35%).",
  analysts: "Consensus rating, how many analysts cover it, estimate revisions in the last 30 days, and the earnings-beat record.",
  insiders: "Genuine open-market buying by executives and directors in the last 60 days. Plan purchases, mismatched prices and 10b5-1 plans are ignored. No buying = 50 (neutral).",
  quality: "Operating margin, return on equity, debt, revenue and earnings growth, positive free cash flow.",
  momentum: "3-month return vs the market, 6-month return, and whether it's above its 50- and 200-day averages.",
  value: "Forward P/E and price-to-sales, ranked within its own sector.",
};

export function renderSystem(view, board) {
  const w = board?.weights || {}, r = board?.rules || {};
  const total = Object.values(w).reduce((a, b) => a + b, 0) || 1;
  view.innerHTML = `<div class="stack">
    <div class="section-head"><h2>How the system works</h2></div>
    <div class="hud"><div class="in stack">
      <p class="t2" style="margin:0">Every weekday evening it scores ~${board?.ranked_n?.toLocaleString() ?? "1,800"} liquid US and Canadian stocks on six pillars.
        Each pillar ranks a stock against all the others (70 = better than 70% of them). The pillars blend into one <b>Conviction</b> score,
        minus a risk penalty, plus a small bonus for Canadian listings.</p>
      <div class="table-wrap"><table class="data"><thead><tr><th>Pillar</th><th class="num">Weight</th><th>What it measures</th></tr></thead><tbody>
        ${PILLARS.map(([k, name]) => `<tr><td><b>${name}</b></td><td class="num"><span class="mini"><i style="width:${(w[k] / total) * 100 * 3}%"></i></span>${w[k] ?? 0}</td>
          <td class="t2" style="white-space:normal">${esc(WHAT[k])}</td></tr>`).join("")}
        <tr><td><b>Risk</b></td><td class="num">−15 max</td><td class="t2" style="white-space:normal">Very volatile, tiny company, heavy debt, heavy short selling, no analyst coverage, or earnings inside the trade window.</td></tr>
      </tbody></table></div>
      <h3>A stock becomes a top idea when</h3>
      <ul class="t2 small" style="margin:0;padding-left:18px;line-height:1.8">
        <li>it ranks among the highest on Conviction (one idea per sector)</li>
        <li>upside is at least ${Math.round((r.min_upside ?? 0.08) * 100)}% (analyst target or swing target)</li>
        <li>quality is above ${r.min_quality ?? 25} and the risk penalty is ${r.max_penalty ?? 9} or less</li>
        <li>the chart says the trend has turned up (not still falling, not overextended)</li>
      </ul>
      <h3>Every idea comes with a plan</h3>
      <p class="t2 small" style="margin:0">Buy zone around today's price, a stop 2× the stock's average daily move below, a target at least 2× the risk above,
        and a 15-trading-day time limit. Set your account size in Holdings and each plan tells you how many shares to buy.</p>
      <p class="tiny muted" style="margin:0">Weights live in <code>config/weights.yaml</code> and change only when you edit them. Data: SEC EDGAR, Yahoo Finance (free).
        Fundamentals refresh on a rolling weekly cycle; prices and insider filings daily. Not financial advice.</p>
    </div></div>
  </div>`;
}
