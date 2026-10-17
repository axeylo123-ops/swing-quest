// The Reckoning (System Health): a weekly boss fight. Each face-down rune is one
// scoring factor; flipping it reveals whether that factor is helping, and hits
// the Shadow of Doubt. Reveal them all to win the week's XP and see the spoils
// (suggested weight changes, which you approve yourself in config/weights.yaml).
import { esc, pct, niceDate, weekKey, todayStr } from "./util.js";
import { boss, flourish } from "./art.js";
import * as fx from "./fx.js";
import * as game from "./game.js";

const FACTORS = {
  cluster: { label: "Insider Cluster", glyph: "ᚲ", what: "Several different insiders buying within 30 days." },
  role: { label: "Buyer's Rank", glyph: "ᚱ", what: "CEOs and CFOs earn more points than directors, then officers, then big outside investors." },
  dollar_size: { label: "Gold Committed", glyph: "ᚷ", what: "How many dollars the insiders spent in total." },
  stake_increase: { label: "Stake Increase", glyph: "ᛋ", what: "How much the purchase grew the insider's existing holding." },
  first_buy: { label: "First Buy in a Year", glyph: "ᚠ", what: "The insider hadn't bought in the previous 12 months." },
  price_context: { label: "Near the Valley", glyph: "ᚹ", what: "The stock is trading near its 52-week low." },
};
const VERDICTS = {
  helping: { cls: "open", text: "Helping", say: "Signals where this was strong beat the others." },
  hurting: { cls: "fled", text: "Hurting", say: "Signals where this was strong did WORSE than the others. Its weight may be too high." },
  unclear: { cls: "blocked", text: "Unclear", say: "No meaningful difference either way yet." },
  "not enough data": { cls: "blocked", text: "Not enough data", say: "Fewer than 30 signals on one side, so it can't be judged yet." },
};

// Same rule as swingquest/health.py: strong-vs-weak difference of at least
// 0.5% in 15-day return vs the market.
function fromScorecard(card, weights) {
  return {
    preview: true,
    factors: Object.entries(card.by_factor).map(([name, f]) => {
      let verdict = "unclear";
      if (!f.enough_data || f.edge_excess_15 == null) verdict = "not enough data";
      else if (f.edge_excess_15 >= 0.005) verdict = "helping";
      else if (f.edge_excess_15 <= -0.005) verdict = "hurting";
      return { name, weight: weights?.[name], edge: f.edge_excess_15, with_n: f.with.n, without_n: f.without.n, verdict };
    }),
    suggestions: [], observations: [], improvements: [],
  };
}

export function renderHealth(view, health, scorecard, today) {
  if (!health && scorecard?.backtest) health = fromScorecard(scorecard.backtest, today?.rules?.weights);
  if (!health) {
    view.innerHTML = `<div class="panel framed hero-panel"><div class="big">No Reckoning yet</div><p>It appears after the first backtest.</p></div>`;
    return;
  }
  const week = health.week || weekKey(todayStr());
  const won = game.get().healthWeeks.includes(week);
  const total = health.factors.length;
  let revealed = won ? total : 0;

  view.innerHTML = `<div class="stack">
    <div class="panel framed hero-panel">
      <div class="kicker">The Reckoning · ${health.preview ? "preview from the backtest" : `week of ${esc(niceDate(week))}`}</div>
      <div class="big">Face the Shadow of Doubt</div>
      <p>Each rune is one part of the score. Flip them all to learn which parts truly predict better quests and which only look clever.
        Defeat the Shadow to earn <strong>+${game.XP.health} XP</strong>.</p>
    </div>

    <div class="panel framed on-dark">
      <div class="arena">
        <div>${boss(won)}</div>
        <div>
          <div class="spread"><h3>Shadow of Doubt</h3><span class="muted small" id="hp-text"></span></div>
          <div class="hp"><i id="hp" style="width:100%"></i></div>
          <p class="muted" id="boss-line" style="margin:4px 0 0"></p>
        </div>
      </div>
    </div>

    <div class="runes-grid">
      ${health.factors.map((f) => {
        const info = FACTORS[f.name] || { label: f.name, glyph: "ᛟ", what: "" }, v = VERDICTS[f.verdict] || VERDICTS.unclear;
        return `<button type="button" class="rune ${won ? "revealed" : ""}" data-f="${esc(f.name)}" aria-label="Reveal ${esc(info.label)}">
          <div class="rune-inner">
            <div class="rune-face rune-back"><div class="glyph">${info.glyph}</div><div class="hint">${esc(info.label)}</div><div class="hint" style="opacity:.6">tap to reveal</div></div>
            <div class="rune-face rune-front">
              <div class="spread"><span class="fname">${esc(info.label)}</span><span class="chip ${v.cls}">${v.text}</span></div>
              <div class="edge" style="color:${f.edge >= 0 ? "var(--treasure)" : "var(--retreat)"}">${pct(f.edge)}</div>
              <p>${esc(v.say)}</p>
              <p style="margin-top:auto;font-size:13px;color:var(--ink-soft)">${esc(info.what)} · ${f.with_n} strong / ${f.without_n} weak${f.weight != null ? ` · weight ${f.weight}` : ""}</p>
            </div>
          </div></button>`;
      }).join("")}
    </div>

    <div id="spoils" ${won ? "" : "hidden"}>
      <div class="section-title"><h2>The Spoils</h2>${flourish()}<p>What the Reckoning suggests. Nothing changes unless you change it.</p></div>
      <div class="panel framed on-dark spoils">
        ${health.suggestions?.length ? `<div class="table-wrap"><table>
          <thead><tr><th>Factor</th><th class="num">Now</th><th class="num">Suggested</th><th>Why</th></tr></thead>
          <tbody>${health.suggestions.map((s) => `<tr><td>${esc(FACTORS[s.factor]?.label || s.factor)}</td><td class="num">${s.current}</td>
            <td class="num"><strong style="color:var(--gold-bright)">${s.suggested}</strong></td><td class="muted">${esc(s.why)}</td></tr>`).join("")}</tbody></table></div>
          <p class="small muted">To accept, copy the numbers from <code>config/weights_proposed.yaml</code> into <code>config/weights.yaml</code>.</p>`
          : `<p class="muted" style="margin:0">${health.preview ? "Suggested weight changes arrive with the first weekly report (Phase 4)." : "No changes suggested this week. The weights hold."}</p>`}
        ${health.observations?.length ? `<h3 style="margin-top:14px">What the Reckoning noticed</h3><ul class="lore">${health.observations.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
        ${health.improvements?.length ? `<h3 style="margin-top:14px">Where to improve</h3><ul class="lore warn">${health.improvements.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
      </div>
    </div>
  </div>`;

  const hp = view.querySelector("#hp"), hpText = view.querySelector("#hp-text"), line = view.querySelector("#boss-line");
  const bossEl = view.querySelector(".boss-svg");
  const update = () => {
    const left = total - revealed;
    hp.style.width = `${(left / total) * 100}%`;
    hpText.textContent = `${left}/${total} HP`;
    line.textContent = left === total ? "\"You trust your score blindly? Prove it.\""
      : left > 0 ? `"${left} rune${left === 1 ? "" : "s"} still hide${left === 1 ? "s" : ""} the truth…"`
      : "The Shadow is vanquished. Doubt has been answered with data.";
  };
  update();
  view.querySelectorAll(".rune").forEach((r) => r.addEventListener("click", () => {
    if (r.classList.contains("revealed")) return;
    r.classList.add("revealed");
    revealed++;
    fx.floatText(bossEl, `-1`, "dmg");
    bossEl.classList.remove("hit"); void bossEl.getBoundingClientRect(); bossEl.classList.add("hit");
    update();
    if (revealed === total) {
      bossEl.classList.add("defeated");
      view.querySelector("#spoils").hidden = false;
      game.healthRead(week, r);
    }
  }));
}
