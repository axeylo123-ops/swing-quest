// The Chronicle (Scorecard): answers "can I trust the quests?" in plain words,
// shows recent form, and lets you ask the Oracle about any kind of past signal.
import { esc, pct, rate, niceDate, signClass } from "./util.js";
import { barChart } from "./charts.js";
import { flourish, emblem, tierOf } from "./art.js";
import { summarize, since, roleGroup, ROLE_GROUPS, MIN_SAMPLES } from "./history.js";
import * as fx from "./fx.js";

function verdict(s) {
  if (!s.enough) return { word: "Too early to tell", runes: 1, advice: "There aren't enough finished quests yet to judge. Treat every quest as an idea to research, not an order." };
  if (s.vsMarket >= 0.01 && s.win >= 0.55) return { word: "Trusted", runes: 5, advice: "Quests have clearly beaten the market. Still follow every retreat (stop-loss): even good systems lose often." };
  if (s.vsMarket >= 0.005) return { word: "Promising", runes: 4, advice: "Quests have beaten the market by a little. Use small positions and keep watching the Chronicle." };
  if (s.vsMarket > -0.005) return { word: "A coin flip vs the market", runes: s.win >= 0.55 ? 3 : 2,
    advice: "Quests made money on average, but about as much as simply holding the market. Treat them as ideas to research, keep positions small, and let the weekly Reckoning improve the weights." };
  return { word: "Not working", runes: 1, advice: "Quests have done worse than the market. Don't trade them until the Reckoning finds what's broken." };
}

function seasonBox(label, s) {
  return `<div class="season"><div class="k">${esc(label)}</div>
    ${s.n ? `<div class="v ${signClass(s.vsMarket)}">${pct(s.vsMarket)}</div><div class="small muted">vs the market · ${s.n} quests</div>
      <div class="small">Won ${rate(s.win)} · avg trade <span class="${signClass(s.avgTrade)}">${pct(s.avgTrade)}</span></div>
      ${s.enough ? "" : '<div class="small" style="color:var(--amber)">Too few to judge</div>'}`
      : '<div class="v muted">–</div><div class="small muted">no finished quests</div>'}</div>`;
}

const FILTERS = {
  which: { label: "Which signals", opts: { "Posted quests": (r) => r.status === "pick", "Quests + rumors": (r) => r.status !== "below", "Everything scored": () => true } },
  rarity: { label: "Rarity (score)", opts: { Any: () => true, "Common <60": (r) => r.score < 60, "Rare 60–69": (r) => tierOf(r.score).name === "Rare",
    "Epic 70–79": (r) => tierOf(r.score).name === "Epic", "Legendary 80+": (r) => r.score >= 80 } },
  buyer: { label: "Top buyer", opts: { Any: () => true, ...Object.fromEntries(Object.entries(ROLE_GROUPS).map(([k, f]) => [k, (r) => f(r.role)])) } },
  price: { label: "Share price", opts: { Any: () => true, "Under $5": (r) => r.entry < 5, "$5–$30": (r) => r.entry >= 5 && r.entry <= 30, "Over $30": (r) => r.entry > 30 } },
  cluster: { label: "Insider cluster", opts: { Any: () => true, "2+ insiders": (r) => r.cluster_points > 0, "Lone buyer": (r) => !r.cluster_points } },
  rs: { label: "Stock vs market (3 months)", opts: { Any: () => true, Beating: (r) => r.rs_3m != null && r.rs_3m >= 0, Lagging: (r) => r.rs_3m != null && r.rs_3m < 0 } },
  sector: { label: "Its sector vs market (3 months)", opts: { Any: () => true, Leading: (r) => r.sector_rs != null && r.sector_rs >= 0, Lagging: (r) => r.sector_rs != null && r.sector_rs < 0 } },
  earnings: { label: "Earnings inside the quest window", opts: { Any: () => true, "No earnings": (r) => r.earnings_in_window === false, "Earnings inside": (r) => r.earnings_in_window === true } },
  path: { label: "Path (timing)", opts: { Any: () => true, "Open (Ready)": (r) => r.timing === "Ready", "Blocked (Wait)": (r) => r.timing === "Wait", "Don't chase": (r) => r.timing === "Extended" } },
};

function lessons(all, card) {
  const out = [];
  const groups = Object.keys(ROLE_GROUPS).map((g) => ({ g, ...summarize(all.filter((r) => roleGroup(r.role) === g)) })).filter((x) => x.enough);
  if (groups.length >= 2) {
    groups.sort((a, b) => b.vsMarket - a.vsMarket);
    const best = groups[0], worst = groups[groups.length - 1];
    out.push(`Follow the right insiders: when the top buyer was a <strong>${esc(best.g)}</strong>, signals beat the market by ${pct(best.vsMarket)} on average.
      When it was a <strong>${esc(worst.g)}</strong>: ${pct(worst.vsMarket)}.`);
  }
  const hi = summarize(all.filter((r) => r.score >= 60)), lo = summarize(all.filter((r) => r.score < 60));
  if (hi.enough && lo.enough) {
    out.push(hi.vsMarket > lo.vsMarket + 0.002
      ? `Higher scores help a little: signals scoring 60+ did ${pct(hi.vsMarket)} vs the market, compared with ${pct(lo.vsMarket)} below 60.`
      : `The score isn't separating winners well yet: 60+ did ${pct(hi.vsMarket)} vs the market, below 60 did ${pct(lo.vsMarket)}. The Reckoning will suggest new weights.`);
  }
  const ready = summarize(all.filter((r) => r.timing === "Ready")), wait = summarize(all.filter((r) => r.timing === "Wait"));
  if (ready.enough && wait.enough && Math.abs(ready.vsMarket - wait.vsMarket) > 0.002) {
    out.push(ready.vsMarket > wait.vsMarket
      ? `Waiting for an open path pays: "Ready" signals did ${pct(ready.vsMarket)} vs the market, "Wait" signals ${pct(wait.vsMarket)}.`
      : `The path (timing) label isn't helping yet: "Ready" signals did ${pct(ready.vsMarket)} vs the market, "Wait" signals ${pct(wait.vsMarket)}.`);
  }
  const p = card?.picks;
  if (p?.time_exit != null && p.time_exit > 0.5) {
    out.push(`Most quests end at the return-by date (${rate(p.time_exit)}): the treasure (target) was reached first only ${rate(p.target_first)} of the time, the retreat (stop) ${rate(p.stop_first)}. The target may be too far for a 15-day quest.`);
  }
  return out;
}

function table(groups) {
  const rows = Object.entries(groups || {});
  return `<div class="table-wrap"><table><thead><tr><th>Group</th><th class="num">Signals</th><th class="num">Beat market</th>
    <th class="num">vs market</th><th class="num">Won</th><th class="num">Avg trade</th></tr></thead>
    <tbody>${rows.map(([k, s]) => `<tr><td>${esc(k)}${s.enough_data ? "" : ' <span class="chip lowdata">few</span>'}</td><td class="num">${s.n}</td>
      <td class="num">${rate(s.beat_spy_rate)}</td><td class="num ${signClass(s.avg_excess_15)}">${pct(s.avg_excess_15)}</td>
      <td class="num">${rate(s.win_rate)}</td><td class="num ${signClass(s.avg_trade_return)}">${pct(s.avg_trade_return)}</td></tr>`).join("")}</tbody></table></div>`;
}

export function renderScorecard(view, card, all = []) {
  if (!all.length) {
    view.innerHTML = `<div class="panel framed hero-panel"><div class="big">The Chronicle is empty</div><p>Run <code>python -m swingquest backtest</code> to write it.</p></div>`;
    return;
  }
  const quests = all.filter((r) => r.status === "pick");
  const s = summarize(quests), v = verdict(s);
  const first = all[0].signal_date, last = all[all.length - 1].signal_date;
  const won = s.trades ? Math.round(s.win * s.trades) : 0;

  view.innerHTML = `<div class="stack">
    <div class="panel framed hero-panel">
      <div class="kicker">The Chronicle</div>
      <div class="big">Can I trust the quests?</div>
      <p>Every past quest, replayed with only what was known at the time. Buy at the next morning's open, skip it if
        the price already ran past the zone, and count the retreat first if both were hit the same day.</p>
      <p class="small muted">Covers signals from ${esc(niceDate(first))} to ${esc(niceDate(last))}. The newest 3 weeks can't be judged yet:
        a quest needs 15 trading days to finish.</p>
    </div>

    <div class="panel framed on-dark">
      <div class="oracle">
        <div class="center"><div class="eye-orb">${emblem("eye", 60)}</div><div class="runes">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= v.runes ? "lit" : ""}"></i>`).join("")}</div></div>
        <div>
          <h3>The Oracle's verdict</h3>
          <div class="verdict-word">${esc(v.word)}</div>
          <p style="margin:6px 0">Of <strong>${s.trades}</strong> past quests traded, <strong>${won}</strong> made money (${rate(s.win)}).
            The average quest returned <strong class="${signClass(s.avgTrade)}">${pct(s.avgTrade)}</strong> in about three weeks, which is
            <strong class="${signClass(s.vsMarket)}">${pct(s.vsMarket)}</strong> more than simply holding the market (SPY) over the same days.</p>
          <p style="margin:6px 0;color:var(--gold-bright)"><em>What this means for you:</em> ${esc(v.advice)}</p>
        </div>
      </div>
    </div>

    <div class="section-title"><h2>Recent Form</h2>${flourish()}<p>Is it working lately? Results of finished quests, by when they were posted.</p></div>
    <div class="seasons">
      ${seasonBox("Live record (real time)", summarize(quests.filter((r) => r.source === "live")))}
      ${seasonBox("Last 3 months", summarize(since(quests, 3, last)))}
      ${seasonBox("Last 6 months", summarize(since(quests, 6, last)))}
      ${seasonBox("All time", s)}
    </div>

    <div class="section-title"><h2>Ask the Oracle</h2>${flourish()}<p>Pick the kind of signal you're curious about and see how those did in the past.</p></div>
    <div class="panel framed on-dark" id="oracle">
      ${Object.entries(FILTERS).map(([key, f]) => `<div class="chipset" data-filter="${key}"><span class="label">${esc(f.label)}</span>
        ${Object.keys(f.opts).map((o, i) => `<button type="button" data-opt="${esc(o)}" aria-pressed="${i === 0}">${esc(o)}</button>`).join("")}</div>`).join("")}
      <div id="oracle-answer"></div>
    </div>

    <div class="section-title"><h2>Lessons from the Chronicle</h2>${flourish()}</div>
    <div class="panel on-dark"><ul class="lore">${lessons(all, card?.backtest).map((l) => `<li>${l}</li>`).join("") || "<li>Not enough history for lessons yet.</li>"}</ul></div>

    ${card?.backtest?.monthly_picks?.length ? `<div class="panel on-dark"><h3>Quest results by month</h3>
      <p class="muted small" style="margin:2px 0 6px">Average trade return of the quests posted each month. Faded = fewer than 5 quests.</p>
      <div class="chart" id="monthly"></div></div>` : ""}

    ${card?.backtest ? `<div class="panel on-dark">
      <details><summary>Detailed tables: by score</summary>${table(card.backtest.by_score_bucket)}</details>
      <details><summary>Detailed tables: by top buyer</summary>${table(card.backtest.by_role)}</details>
      <details><summary>Detailed tables: by path (timing)</summary>${table(card.backtest.by_timing)}</details>
      <details><summary>Detailed tables: older vs newer half</summary>${table(card.backtest.by_period)}</details>
    </div>` : ""}

    <div class="panel on-dark"><h3>Read this with care</h3><ul class="lore warn" style="margin-top:6px">${(card?.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>
  </div>`;

  wireOracle(view, all);
  const m = view.querySelector("#monthly");
  if (m) {
    const months = card.backtest.monthly_picks;
    barChart(m, months.map((x) => ({ label: x.month.slice(2).replace("-", "/"), value: x.avg_trade_return, lowData: x.n < 5,
      tip: `<strong>${esc(x.month)}</strong><br>${x.n} quest${x.n === 1 ? "" : "s"}<br>Avg trade ${pct(x.avg_trade_return)}` })),
      { format: (val) => pct(val, 0), labelEvery: Math.max(1, Math.ceil(months.length / 8)), height: 170 });
  }
}

function wireOracle(view, all) {
  const box = view.querySelector("#oracle"), out = view.querySelector("#oracle-answer");
  const chosen = Object.fromEntries(Object.entries(FILTERS).map(([k, f]) => [k, Object.keys(f.opts)[0]]));
  const answer = () => {
    const list = all.filter((r) => Object.entries(chosen).every(([k, o]) => FILTERS[k].opts[o](r)));
    const s = summarize(list);
    out.innerHTML = `<div class="answer">
        <div class="tally"><div class="v" data-n>0</div><div class="k">Past cases</div></div>
        <div class="tally"><div class="v" data-win>–</div><div class="k">Trades won</div><div class="meter"><i style="width:${(s.win || 0) * 100}%"></i></div></div>
        <div class="tally"><div class="v ${signClass(s.avgTrade)}" data-avg>–</div><div class="k">Avg trade</div></div>
        <div class="tally"><div class="v ${signClass(s.vsMarket)}" data-vs>–</div><div class="k">vs market</div></div>
      </div>
      <p class="center" style="margin:12px 0 0">${s.n ? `In <strong>${s.n}</strong> past cases like this, ${rate(s.win)} of trades made money and they beat the market
        ${rate(s.beat)} of the time.` : "No past cases match all of these."}
        ${s.n && !s.enough ? `<br><span style="color:var(--amber)">Fewer than ${MIN_SAMPLES} cases: not enough to trust.</span>` : ""}</p>`;
    fx.countUp(out.querySelector("[data-n]"), s.n);
    fx.countUp(out.querySelector("[data-win]"), s.win, (x) => `${Math.round(x * 100)}%`);
    fx.countUp(out.querySelector("[data-avg]"), s.avgTrade, (x) => pct(x));
    fx.countUp(out.querySelector("[data-vs]"), s.vsMarket, (x) => pct(x));
  };
  box.querySelectorAll(".chipset").forEach((set) => set.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    set.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    chosen[set.dataset.filter] = b.dataset.opt;
    answer();
  }));
  answer();
}
