// Paper tab: every practice trade is a bubble that starts as $100. Its AREA
// tracks the price (price doubles = bubble twice as big). The outer ring is the
// target, the inner ring the stop: grow into the outer ring and it pops green,
// shrink into the inner ring and it pops red. Yours and the system's side by side.
import { esc, shortDate, storage } from "./util.js";
import { pct, cls } from "./ui.js";
import * as P from "./paper.js";
import * as fx from "./fx.js";

const R0 = 44;                                  // radius of a $100 bubble, in px
const UI_KEY = "sq.paper.ui";
const REASON = { target: "Target hit", stop: "Stopped out", time: "Time limit", sold: "You sold" };
let playTimer = null;

const radius = (value) => R0 * Math.sqrt(Math.max(value, 1) / P.START);
const money = (x, d = 0) => (x == null ? "–" : `${x < 0 ? "−" : ""}$${Math.abs(x).toFixed(d)}`);
const signed = (x) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}$${Math.abs(x).toFixed(2)}`);

function items(paper, universe) {
  const bars = paper?.bars || {};
  const names = Object.fromEntries((universe?.stocks || []).map((s) => [s.ticker, s.name]));
  const trades = P.load();
  const { graded, changed } = P.gradeMine(trades, bars);
  if (changed) P.save(trades);
  const mine = graded.map(({ t, g }) => ({ id: t.id, owner: "you", t, g, name: t.name || names[t.ticker] || "", why: t.why }));
  const sys = (paper?.system || []).map((p) => ({ id: `sys-${p.id}`, owner: "sys", t: p, g: P.gradeSystem(p, bars[p.ticker]),
    name: names[p.ticker] || "", why: p.reason || "" }));
  return { mine, sys, spy: bars.SPY || [] };
}

function timeline(list, spy, asOf) {
  const starts = list.map((x) => x.g.entryDate).filter(Boolean).sort();
  if (!starts.length) return asOf ? [asOf] : [];
  return [...new Set(spy.map((b) => b[0]).filter((d) => d >= starts[0]).concat(asOf ? [asOf] : []))].sort();
}

// state of one bubble on one day of the replay
function stateOn(x, day, last) {
  const g = x.g;
  if (g.status === "pending") return day === last ? { kind: "pending", value: P.START } : null;
  if (g.status !== "open" && g.status !== "closed") return null;
  const v = P.valueOn(g, day);
  if (v == null) return null;
  if (g.status === "closed" && day === g.exitDate) return { kind: g.reason === "target" || (g.reason !== "stop" && g.ret > 0) ? "won" : "lost", value: v };
  return { kind: v >= P.START ? "up" : "down", value: v };
}

function bubble(x) {
  const pl = x.t.plan, entry = x.g.entry || pl.reference || pl.entry_high;
  const rT = radius(P.START * pl.target / entry), rS = radius(P.START * pl.stop / entry);
  const peak = Math.max(...(x.g.path || []).map((p) => p[1]), P.START);
  const half = Math.ceil(Math.max(rT, radius(peak)) + 6), size = half * 2;
  return `<button class="bub ${x.owner}" data-id="${esc(x.id)}" style="width:${size}px;height:${size + 18}px" aria-label="${esc(x.t.ticker)} paper trade">
    <svg viewBox="${-half} ${-half} ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
      <circle class="ring-t" r="${rT}"/><circle class="ring-s" r="${rS}"/><circle class="ring-0" r="${R0}"/>
      <circle class="core" style="r:${R0}px"/>
      <text class="b-tk" y="-4">${esc(x.t.ticker)}</text><text class="b-v" y="11">$100</text>
    </svg>
    <span class="b-who">${x.owner === "you" ? "YOU" : x.t.kind === "high" ? "SYSTEM · HIGH" : "SYSTEM"}</span>
  </button>`;
}

function paint(root, list, day, last, prev) {
  for (const x of list) {
    const el = root.querySelector(`.bub[data-id="${CSS.escape(x.id)}"]`);
    if (!el) continue;
    const st = stateOn(x, day, last);
    el.hidden = !st;
    if (!st) continue;
    const core = el.querySelector(".core"), r = radius(st.value);
    core.style.r = `${r}px`;
    el.dataset.state = st.kind;
    el.querySelector(".b-v").textContent = st.kind === "pending" ? "next open" : `$${st.value.toFixed(0)} ${pct(st.value / P.START - 1)}`;
    if (prev && prev !== day && (st.kind === "won") && !el.dataset.popped) { el.dataset.popped = "1"; fx.sparks(el, 14); }
    if (st.kind !== "won" && st.kind !== "lost") delete el.dataset.popped;
  }
  const n = list.filter((x) => stateOn(x, day, last)).length;
  root.querySelector(".arena-empty").hidden = n > 0;
}

function scoreCard(title, t, cls_) {
  return `<div class="score ${cls_}"><div class="score-h">${title}</div>
    <div class="score-row"><span>Open</span><b class="mono">${t.open}${t.pending ? ` <small class="muted">+${t.pending} waiting</small>` : ""}</b></div>
    <div class="score-row"><span>Worth now</span><b class="mono">${t.open ? money(t.openValue) : "–"}</b></div>
    <div class="score-row"><span>Finished</span><b class="mono">${t.closed ? `${t.won} won of ${t.closed}` : "–"}</b></div>
    <div class="score-row"><span>Profit / loss</span><b class="mono ${cls(t.pl)}">${t.closed ? signed(t.pl) : "–"}</b></div>
    <div class="score-row"><span>vs the market</span><b class="mono ${cls(t.vsMarket)}">${t.vsMarket != null ? pct(t.vsMarket, 1) + " a trade" : "–"}</b></div>
  </div>`;
}

function shelf(list, spy) {
  const done = list.filter((x) => x.g.status === "closed").sort((a, b) => (b.g.exitDate || "").localeCompare(a.g.exitDate || ""));
  const skipped = list.filter((x) => x.g.status === "skipped");
  if (!done.length && !skipped.length) return `<p class="small muted" style="margin:0">Nothing finished yet. A bubble lands here when it pops (target or stop) or its time limit runs out.</p>`;
  return `${done.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Stock</th><th>Who</th><th>Result</th><th class="num">Return</th>
      <th class="num">$100 became</th><th class="num">Days</th><th class="num">Market</th><th>Reason</th></tr></thead><tbody>
    ${done.map((x) => { const m = P.marketReturn(spy, x.g.entryDate, x.g.exitDate); return `<tr>
      <td><b>${esc(x.t.ticker)}</b></td><td class="tiny">${x.owner === "you" ? "You" : "System"}</td>
      <td><span class="chip ${x.g.ret > 0 ? "buy" : "avoid"}">${esc(REASON[x.g.reason] || x.g.reason)}</span></td>
      <td class="num ${cls(x.g.ret)}">${pct(x.g.ret, 1)}</td><td class="num">${money(x.g.value, 2)}</td>
      <td class="num">${x.g.days ?? "–"}</td><td class="num ${cls(m)}">${m == null ? "–" : pct(m, 1)}</td>
      <td class="tiny t2" style="white-space:normal;min-width:200px">${x.why ? `“${esc(x.why)}”` : '<span class="muted">no reason written</span>'}</td></tr>`; }).join("")}
    </tbody></table></div>` : ""}
    ${skipped.length ? `<p class="tiny muted" style="margin:8px 0 0">${skipped.length} trade${skipped.length > 1 ? "s" : ""} never started:
      ${skipped.map((x) => `${esc(x.t.ticker)} (${esc(x.g.reason || "skipped")})`).join(", ")}.</p>` : ""}`;
}

function detail(x, open, refresh) {
  if (!x) return "";
  const g = x.g, pl = x.t.plan, mine = x.owner === "you";
  const status = g.status === "pending" ? `Waiting to buy at the open on ${esc(shortDate(g.fillOn || x.t.fillOn))}`
    : g.status === "open" ? `Day ${g.days} of ${g.timeStop} · bought at ${g.entry.toFixed(2)} on ${esc(shortDate(g.entryDate))}${g.aboveZone ? " (above the buy zone)" : ""}`
    : g.status === "closed" ? `${esc(REASON[g.reason] || g.reason)} on ${esc(shortDate(g.exitDate))} after ${g.days} days · bought ${g.entry.toFixed(2)}, sold ${g.exitPrice.toFixed(2)}`
    : esc(g.reason || "No price data for this trade");
  return `<div class="pp-detail">
    <div class="spread"><div><b style="font-size:18px">${esc(x.t.ticker)}</b> <span class="muted small">${esc(x.name)}</span>
      <span class="tiny ${mine ? "neon" : "cyan"}">· ${mine ? "your trade" : "system pick"}</span></div>
      ${g.value != null ? `<b class="mono ${cls(g.ret)}" style="font-size:20px">$100 → ${money(g.value, 2)}</b>` : ""}</div>
    <div class="small t2">${status}</div>
    <div class="tiny muted">Stop ${pl.stop.toFixed(2)} · target ${pl.target.toFixed(2)} · ${pl.time_stop_days}-day limit</div>
    ${mine ? `<label class="tiny muted" style="display:block;margin-top:6px">WHY I BOUGHT IT
        <input class="field" id="pp-why" maxlength="140" value="${esc(x.t.why || "")}" placeholder="One line: what you saw in it"></label>`
      : x.why ? `<div class="small">System's reason: <span class="t2">${esc(x.why)}</span></div>` : ""}
    <div class="row" style="margin-top:8px">
      <button class="btn" data-act="dossier">Open dossier</button>
      ${mine ? `<button class="btn" data-act="save">Save note</button>` : ""}
      ${mine && g.status === "open" ? `<button class="btn" data-act="sell">Sell now (last close)</button>` : ""}
      ${mine ? `<button class="btn" data-act="delete">Delete</button>` : ""}
    </div></div>`;
}

export function renderPaper(view, paper, board, universe, open) {
  stopPaper();
  const ui = { filter: "both", ...storage.get(UI_KEY, {}) };
  const { mine, sys, spy } = items(paper, universe);
  const shown = () => (ui.filter === "you" ? mine : ui.filter === "sys" ? sys : [...mine, ...sys]);
  const days = timeline([...mine, ...sys], spy, paper?.as_of);
  let di = days.length - 1, selected = null;
  const last = days.at(-1);

  view.innerHTML = `<div class="stack paper-view">
    <div class="spread">
      <div><h1 style="font-size:26px;letter-spacing:.12em">Paper trading</h1>
        <div class="small muted">Practice with $100 bubbles. Nothing real is bought. Your trades stay in this browser.</div></div>
      <div class="seg" id="pp-filter">${[["both", "Both"], ["you", "Yours"], ["sys", "System"]].map(([k, l]) =>
        `<button data-v="${k}" aria-pressed="${ui.filter === k}">${l}</button>`).join("")}</div>
    </div>
    <div class="scores">${scoreCard("You", P.totals(mine, spy), "you")}${scoreCard("The system", P.totals(sys, spy), "sys")}</div>
    <div class="hud"><div class="in">
      <div class="spread"><b class="mono" id="pp-day"></b>
        <span class="tiny muted legend"><i class="lg-t"></i> target ring <i class="lg-s"></i> stop ring <i class="lg-0"></i> $100 start</span></div>
      <div class="arena" id="arena">${shown().filter((x) => ["open", "closed", "pending"].includes(x.g.status)).map(bubble).join("")}
        <div class="arena-empty small muted">${mine.length ? "No bubbles on this day." : "No bubbles yet. Open any top idea, high-upside or watchlist stock and press <b>Paper buy $100</b>."}</div></div>
      ${days.length > 1 ? `<div class="replay"><button class="btn" id="pp-play" aria-label="Play the replay">▶ Replay</button>
        <input type="range" id="pp-range" min="0" max="${days.length - 1}" value="${di}" aria-label="Replay day"></div>` : ""}
      <div id="pp-detail"></div>
    </div></div>
    <div class="hud"><div class="in"><div class="section-head"><h2>Finished trades</h2></div>${shelf(shown(), spy)}</div></div>
    <p class="tiny muted" style="margin:0">How it's graded: bought at the next market open after you click. The plan's stop and target decide the exit
      (if both are touched the same day, the stop counts; an overnight gap gives you the opening price), otherwise it's sold at the close of the last day.
      The system's bubbles follow the same rules and skip any stock that opens above its buy zone. Prices update every weekday evening.</p>
  </div>`;

  const arena = view.querySelector("#arena"), label = view.querySelector("#pp-day"), range = view.querySelector("#pp-range");
  const setDay = (i, prev) => {
    di = i;
    label.textContent = days[i] ? `${shortDate(days[i])}${days[i] === last ? " · latest" : ""}` : "";
    paint(arena, shown(), days[i], last, prev);
    if (range) range.value = i;
  };
  setDay(di);
  const showDetail = () => {
    const box = view.querySelector("#pp-detail"), x = shown().find((y) => y.id === selected);
    box.innerHTML = detail(x, open);
    arena.querySelectorAll(".bub").forEach((b) => b.classList.toggle("sel", b.dataset.id === selected));
    if (!x) return;
    box.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      const trades = P.load(), t = trades.find((y) => y.id === x.id);
      if (b.dataset.act === "dossier") return open(x.t.ticker, b);
      if (!t) return;
      if (b.dataset.act === "save") t.why = view.querySelector("#pp-why").value.trim().slice(0, 140);
      if (b.dataset.act === "sell") t.closeOn = paper.as_of;
      if (b.dataset.act === "delete" && !confirm(`Delete your ${t.ticker} paper trade?`)) return;
      P.save(b.dataset.act === "delete" ? trades.filter((y) => y.id !== t.id) : trades);
      renderPaper(view, paper, board, universe, open);
    }));
  };
  arena.addEventListener("click", (e) => {
    const b = e.target.closest(".bub");
    if (!b) return;
    selected = selected === b.dataset.id ? null : b.dataset.id;
    showDetail();
  });
  range?.addEventListener("input", () => { stopPaper(); setDay(+range.value); });
  view.querySelector("#pp-play")?.addEventListener("click", () => {
    if (playTimer) { stopPaper(); return; }
    let i = di >= days.length - 1 ? 0 : di;
    setDay(i);
    view.querySelector("#pp-play").textContent = "❚❚ Pause";
    playTimer = setInterval(() => {
      if (i >= days.length - 1) { stopPaper(); view.querySelector("#pp-play").textContent = "▶ Replay"; return; }
      const prev = days[i];
      setDay(++i, prev);
    }, fx.calm() ? 50 : 650);
  });
  view.querySelectorAll("#pp-filter button").forEach((b) => b.addEventListener("click", () => {
    storage.set(UI_KEY, { ...ui, filter: b.dataset.v });
    renderPaper(view, paper, board, universe, open);
  }));
}

export function stopPaper() { clearInterval(playTimer); playTimer = null; }

// The buy box shown in a stock's dossier.
export function buyBox(s, board) {
  const listed = ["top", "high", "high_wait", "watch"].some((k) => (board?.[k] || []).some((x) => x.ticker === s.ticker));
  if (!s.plan) return "";
  if (!listed) return `<div class="tiny muted">Paper trading covers stocks on today's lists (top ideas, high-upside, watchlist), so their prices can be tracked.</div>`;
  const fill = P.fillOn();
  const held = P.load().filter((t) => t.ticker === s.ticker && !t.result).length;
  return `<div class="buybox" id="buybox">
    <div class="spread"><b class="small">Paper buy $100</b><span class="tiny muted">fills at the open on ${esc(shortDate(fill))} · practice only</span></div>
    <input class="field" id="pp-new-why" maxlength="140" placeholder="Why are you buying it? (one line, optional)">
    <div class="row"><button class="btn primary" id="pp-buy">Buy $100 bubble</button>
      ${held ? `<span class="tiny neon">You already have ${held} open bubble${held > 1 ? "s" : ""} on ${esc(s.ticker)}</span>` : ""}</div>
  </div>`;
}

export function wireBuy(root, s, onDone) {
  const btn = root.querySelector("#pp-buy");
  btn?.addEventListener("click", () => {
    const trades = P.load();
    trades.push(P.newTrade(s, root.querySelector("#pp-new-why").value));
    P.save(trades);
    fx.sparks(btn, 16);
    onDone?.();
  });
}
