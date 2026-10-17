// The Quest Board (Today): quest scrolls for picks, pinned rumors for the
// watchlist, and a ledger of rejected leads.
import { esc, price, pct, money, rate, niceDate, shortDate, addTradingDays, $$, signClass } from "./util.js";
import { gem, tierOf, noticeBoard, flourish } from "./art.js";
import { priceChart } from "./charts.js";
import { similar, MIN_SAMPLES } from "./history.js";
import * as fx from "./fx.js";
import * as game from "./game.js";

const PATH = {
  Ready: { cls: "open", text: "Path open", plain: "Ready" },
  Wait: { cls: "blocked", text: "Path blocked", plain: "Wait" },
  Extended: { cls: "fled", text: "Don't chase", plain: "Extended" },
};
const FACTOR_NAMES = {
  cluster: "Insider cluster", role: "Buyer's rank", dollar_size: "Gold committed ($)",
  stake_increase: "Stake increase", first_buy: "First buy in 12 months", price_context: "Near 52-week low",
};
const VOWS = [
  "I enter only inside the buy zone, or not at all",
  "I place my retreat (stop-loss) order right away",
  "I leave at the treasure, the retreat, or the return-by date",
];

const pathChip = (label) => { const p = PATH[label] || PATH.Wait; return `<span class="chip ${p.cls}">${p.text} · ${p.plain}</span>`; };

function omen(p, hist) {
  if (!hist.length) return "";
  const s = similar(hist, p.score, topRole(p));
  return `<div class="omen">
    <div class="verdict">Quests like this in the Chronicle</div>
    <div class="small">${esc(s.tier)} quests where the top buyer was ${esc(s.group)}:
      <strong>${s.n}</strong> past cases${s.n ? ` · won <strong>${rate(s.win)}</strong> of trades · average trade
      <strong class="${signClass(s.avgTrade)}">${pct(s.avgTrade)}</strong> · vs the market <strong class="${signClass(s.vsMarket)}">${pct(s.vsMarket)}</strong>` : ""}
      ${s.enough ? "" : `<br><em>Fewer than ${MIN_SAMPLES} past cases: not enough history to lean on.</em>`}</div>
  </div>`;
}
const RANK = ["CEO", "CFO", "Director", "Officer", "10% Owner", "Other"];
const topRole = (p) => p.insiders.map((b) => b.role).sort((a, b) => RANK.indexOf(a) - RANK.indexOf(b))[0];

function questScroll(p, asOf, hist) {
  const g = game.get();
  const reviewed = !!g.reviewed[p.id], sworn = !!g.ruleChecks[p.id];
  const pl = p.plan, tier = tierOf(p.score);
  const sellBy = addTradingDays(addTradingDays(asOf, 1), pl.time_stop_days - 1);
  return `
  <article class="scroll" data-id="${esc(p.id)}">
    ${reviewed ? '<div class="stamped" data-static></div>' : ""}
    <div class="quest-head">
      <div class="name">
        <div class="ticker">${esc(p.ticker)}</div>
        <div class="company">${esc(p.company || "")}</div>
        <div class="rarity ${tier.name.toLowerCase()}">${tier.name} quest</div>
      </div>
      ${gem(p.score, 70)}
    </div>

    <div class="terms">
      <div><div class="k">Enter at</div><div class="plain">buy zone</div><div class="v">${pl.entry_low.toFixed(2)}–${pl.entry_high.toFixed(2)}</div></div>
      <div class="retreat"><div class="k">Retreat</div><div class="plain">stop-loss</div><div class="v">${pl.stop.toFixed(2)}</div></div>
      <div class="treasure"><div class="k">Treasure</div><div class="plain">target</div><div class="v">${pl.target.toFixed(2)}</div></div>
      <div><div class="k">Return by</div><div class="plain">time limit</div><div class="v">${esc(shortDate(sellBy))}</div></div>
    </div>
    <div class="muted small">Risk ${pct(pl.risk_pct, 1, false)} down to the retreat · treasure is ${pl.reward_risk}× that risk
      (at least ${pl.reward_risk_worst}× even if you enter at the top of the zone)</div>

    <div class="two-col">
      <div><h3>Why this quest</h3>
        <ul class="lore">${p.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        ${p.cautions.length ? `<ul class="lore warn" style="margin-top:4px">${p.cautions.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}</div>
      <div><h3>The path</h3>${pathChip(p.timing)}
        <ul class="lore path" style="margin-top:6px">${p.timing_notes.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
    </div>

    <div class="chart" data-chart="${esc(p.id)}"></div>
    ${omen(p, hist)}

    <details>
      <summary>The insiders (${p.insiders.length}) and how the score was earned</summary>
      <div class="table-wrap"><table>
        <thead><tr><th>Insider</th><th>Rank</th><th class="num">Bought</th><th class="num">Avg price</th><th>Filed</th></tr></thead>
        <tbody>${p.insiders.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.role)}</td><td class="num">${money(b.value)}</td>
          <td class="num">${price(b.avg_price)}</td><td>${esc(shortDate(b.filed_date))}</td></tr>`).join("")}</tbody></table></div>
      <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>Factor</th><th class="num">Points</th></tr></thead>
        <tbody>${Object.entries(p.factors).map(([k, f]) => `<tr><td>${esc(FACTOR_NAMES[k] || k)}</td><td class="num">${f.points}</td></tr>`).join("")}</tbody></table></div>
    </details>

    <div class="actions">
      <button class="btn ${reviewed ? "done" : "seal"}" data-review ${reviewed ? "disabled" : ""}>${reviewed ? "Reviewed" : `Seal as reviewed · +${game.XP.review} XP`}</button>
      <button class="btn ${sworn ? "done" : ""}" data-oath-open ${sworn ? "disabled" : ""}>${sworn ? "Oath sworn" : `Swear the oath · +${game.XP.rules} XP`}</button>
    </div>
    <div class="oath" hidden>
      <h3 style="margin-bottom:4px">The Trader's Oath</h3>
      <div class="muted small" style="margin-bottom:6px">XP is for keeping your rules, never for trading more. Passing on a quest counts.</div>
      ${VOWS.map((v, i) => `<label class="vow"><input type="checkbox" data-vow="${i}"><span>${esc(v)}</span></label>`).join("")}
      <label class="vow"><input type="checkbox" data-pass><span><em>Or:</em> I'm passing on this quest on purpose</span></label>
      <button class="btn seal" data-oath-seal style="margin-top:8px">Seal the oath</button>
    </div>
  </article>`;
}

function rumor(p, i) {
  return `<div class="note" style="--r:${[-2, 1.5, -1, 2][i % 4]}deg">
    <div class="spread"><div><div class="ticker">${esc(p.ticker)}</div><div class="company small">${esc(p.company || "")}</div></div>${gem(p.score, 46)}</div>
    <div style="margin:8px 0 4px">${pathChip(p.timing)}</div>
    <ul class="lore small">${p.reasons.slice(0, 3).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <div class="small" style="margin-top:6px;color:var(--ink-2)"><em>${esc(p.timing_notes[0] || "")}</em></div>
  </div>`;
}

export function renderToday(view, data, hist = []) {
  if (!data) {
    view.innerHTML = `<div class="panel framed hero-panel">${noticeBoard()}<div class="big">No scan yet</div>
      <p>Run <code>python -m swingquest scan</code> to post tonight's quests.</p></div>`;
    return;
  }
  const s = data.summary, none = data.status === "none";
  view.innerHTML = `
  <div class="stack">
    <div class="panel framed hero-panel">
      <div class="kicker">The Quest Board · ${esc(niceDate(data.as_of))}</div>
      ${none ? `<div class="empty-board">${noticeBoard()}</div>` : ""}
      <div class="big">${none ? "The board is empty tonight" : `${data.picks.length} quest${data.picks.length > 1 ? "s" : ""} posted`}</div>
      <p>${none ? "No stock passed every rule. Patience is a weapon: a hero who waits beats one who forces a fight."
               : `Each passed the rules, scored ${data.rules.min_score}+ and has an open path. Read the scroll, then decide.`}</p>
      <div class="tallies">
        <div class="tally"><div class="v">${s.insider_buys_in_window}</div><div class="k">Insider buys</div><div class="s">last 30 days</div></div>
        <div class="tally"><div class="v">${s.stocks_with_new_buys}</div><div class="k">Leads examined</div><div class="s">new this week</div></div>
        <div class="tally"><div class="v">${s.watchlist}</div><div class="k">Rumors</div><div class="s">good, not ready yet</div></div>
        <div class="tally"><div class="v">${s.skipped}</div><div class="k">Rejected</div><div class="s">failed a rule</div></div>
      </div>
    </div>

    ${data.picks.length ? `<div class="section-title"><h2>Tonight's Quests</h2>${flourish()}</div>
      <div class="stack">${data.picks.map((p) => questScroll(p, data.as_of, hist)).join("")}</div>` : ""}

    ${data.watchlist.length ? `<div class="section-title"><h2>Rumors</h2>${flourish()}
      <p>Strong insider buying, but the path isn't open yet. Not a buy, just one to watch.</p></div>
      <div class="notes">${data.watchlist.map(rumor).join("")}</div>` : ""}

    <div class="panel on-dark">
      <details ${none && !data.watchlist.length ? "open" : ""}>
        <summary>Rejected leads: why ${data.skipped.length} other stocks didn't make the board</summary>
        <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>Stock</th><th>Reason</th></tr></thead>
        <tbody>${data.skipped.map((k) => `<tr><td><strong>${esc(k.ticker)}</strong></td><td class="muted">${esc(k.reason)}</td></tr>`).join("")}</tbody></table></div>
      </details>
    </div>
    <p class="muted small center">Posted ${esc(new Date(data.generated_at).toLocaleString())} · minimum score ${data.rules.min_score} · weights live in config/weights.yaml</p>
  </div>`;

  for (const p of data.picks) {
    const card = view.querySelector(`[data-id="${CSS.escape(p.id)}"]`);
    priceChart(card.querySelector("[data-chart]"), p.chart, p.plan);
    const st = card.querySelector("[data-static]");
    if (st) { st.remove(); fx.stamp(card); }
    fx.tilt(card, 2.5);
    wireCard(card, p);
  }
}

function wireCard(card, p) {
  const review = card.querySelector("[data-review]");
  review.addEventListener("click", () => {
    if (review.disabled) return;
    fx.stamp(card);
    game.reviewPick(p.id, p.ticker, review);
    review.disabled = true; review.className = "btn done"; review.textContent = "Reviewed";
  });
  const open = card.querySelector("[data-oath-open]"), oath = card.querySelector(".oath");
  open.addEventListener("click", () => { if (!open.disabled) oath.hidden = !oath.hidden; });
  card.querySelector("[data-oath-seal]").addEventListener("click", (e) => {
    const vows = $$("[data-vow]", oath).map((c) => c.checked), passed = oath.querySelector("[data-pass]").checked;
    if (!passed && !vows.every(Boolean)) {
      fx.shake(oath);
      game.toast("The oath is incomplete", "Keep every vow, or mark that you're passing on purpose");
      return;
    }
    game.ruleCheck(p.id, p.ticker, { vows, passed }, e.currentTarget);
    oath.hidden = true; open.disabled = true; open.className = "btn done"; open.textContent = "Oath sworn";
  });
}
