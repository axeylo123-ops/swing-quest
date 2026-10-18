// System: how the ranking works, its weights and rules, in plain words.
import { esc } from "./util.js";
import { PILLARS } from "./ui.js";

const WHAT = {
  upside: "Realistic analyst upside: the average target vs today's price, trusted less with few analysts or when their targets disagree widely, and capped at +40% (bigger gaps are usually stale targets).",
  analysts: "Consensus rating, coverage, estimate raises vs cuts per analyst (30 days), the trend in this year's EPS estimate, and the earnings-beat record.",
  insiders: "Genuine open-market buying by executives and directors in the last 60 days. Plan purchases, mismatched prices and 10b5-1 plans are ignored. No buying = 50 (neutral).",
  quality: "Operating margin, return on equity, debt, revenue and earnings growth, positive free cash flow.",
  momentum: "3-month return vs the market, 6-month return, how close it is to its 52-week high, and whether it's above its 50- and 200-day averages.",
  value: "Forward P/E and price-to-sales, ranked against its own industry (or sector when the industry is small).",
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
        <tr><td><b>Risk</b></td><td class="num">−15 max</td><td class="t2" style="white-space:normal">Very volatile, small or tiny company, heavy debt, heavy short selling, no analyst coverage, analysts cutting estimates, or earnings inside the trade window.</td></tr>
      </tbody></table></div>
      <h3>A stock becomes a top idea when</h3>
      <ul class="t2 small" style="margin:0;padding-left:18px;line-height:1.8">
        <li>it ranks among the highest on Conviction (one idea per sector)</li>
        <li>realistic upside is at least ${Math.round((r.min_upside ?? 0.08) * 100)}% and analysts aren't cutting estimates</li>
        <li>quality is above ${r.min_quality ?? 25} and the risk penalty is ${r.max_penalty ?? 9} or less</li>
        <li>the chart says the trend has turned up (not still falling, not overextended) and no earnings report is due inside the trade window</li>
      </ul>
      <h3>Every idea comes with a plan</h3>
      <p class="t2 small" style="margin:0">Buy zone around today's price. The stop sits just under real chart support (a recent low or the 50-day average);
        the target is the nearest resistance (recent high, 52-week high or analyst target) that pays at least 2× the risk. 15-trading-day time limit.
        Set your account size in Holdings and each plan tells you how many shares to buy.</p>
      <h3>High-upside lane</h3>
      <p class="t2 small" style="margin:0">A separate, riskier lane: analysts' average target is 50%+ above today (3+ analysts), with at least two separate catalysts
        (genuine insider buying, rising estimates, a big earnings beat, a breakout), a real business, and a chart that has turned up. Wider stop, 30-day limit, size smaller.
        When the chart is still falling it shows as "waiting".</p>
      <p class="tiny muted" style="margin:0">Weights live in <code>config/weights.yaml</code> and change only when you edit them. Data: SEC EDGAR, Yahoo Finance (free).
        Fundamentals refresh on a rolling weekly cycle; prices and insider filings daily. Not financial advice.</p>
    </div></div>
  </div>`;
}
