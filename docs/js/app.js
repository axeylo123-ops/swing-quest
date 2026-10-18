// Swing Quest command center: loads the data, routes between sections,
// powers search and the dossier.
import { $, $$, esc, loadJSON, niceDate } from "./util.js";
import { chip, pct, cls } from "./ui.js";
import * as game from "./game.js";
import { renderCommand } from "./command.js";
import { renderScanner } from "./scanner.js";
import { renderHoldings } from "./holdings.js";
import { renderRecord } from "./record.js";
import { renderSystem } from "./system.js";
import { openDossier } from "./dossier.js";

const data = {};
const view = $("#view");
const TABS = ["command", "scanner", "holdings", "record", "system"];
const open = (ticker, origin) => openDossier(ticker, data.board, data.universe, origin);

function render() {
  const tab = TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "command";
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (tab === "command") renderCommand(view, data.board, data.universe, open);
  else if (tab === "scanner") renderScanner(view, data.universe, open);
  else if (tab === "holdings") renderHoldings(view, data.universe, open);
  else if (tab === "record") renderRecord(view, data.record, data.scorecard);
  else renderSystem(view, data.board);
}

function renderStatus() {
  const b = data.board, m = b?.market;
  $("#status").innerHTML = [
    m ? `<span class="pill ${m.trend === "up" ? "on" : "off"}"><i></i>Market ${m.trend === "up" ? "uptrend" : "downtrend"}</span>` : "",
    b ? `<span class="pill on"><i></i>${b.ranked_n.toLocaleString()} stocks ranked</span>` : "",
    b ? `<span class="pill"><i></i>Data ${esc(niceDate(b.as_of))}</span>` : "",
  ].join("");
}

// Instant search over the whole universe.
function wireSearch() {
  const input = $("#search"), box = $("#results");
  let sel = 0, hits = [];
  const show = () => {
    const q = input.value.trim().toUpperCase();
    if (!q) { box.hidden = true; return; }
    const stocks = data.universe?.stocks || [];
    hits = stocks.filter((s) => s.ticker.startsWith(q)).concat(stocks.filter((s) => !s.ticker.startsWith(q) && (s.name || "").toUpperCase().includes(q))).slice(0, 8);
    sel = 0;
    box.innerHTML = hits.length ? hits.map((s, i) => `<button class="${i === 0 ? "sel" : ""}" data-t="${esc(s.ticker)}">
      <b>${esc(s.ticker)}</b><span class="tiny t2" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.name || "")}</span>
      <span class="mono neon">${Math.round(s.conviction)}</span></button>`).join("")
      : `<div class="tiny muted" style="padding:10px">Not in the ranked universe.</div>`;
    box.hidden = false;
    box.querySelectorAll("button").forEach((b) => b.addEventListener("mousedown", (e) => { e.preventDefault(); pick(b.dataset.t); }));
  };
  const pick = (t) => { box.hidden = true; input.value = ""; input.blur(); open(t); };
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    const btns = [...box.querySelectorAll("button")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + btns.length) % Math.max(1, btns.length);
      btns.forEach((b, i) => b.classList.toggle("sel", i === sel));
    } else if (e.key === "Enter" && hits[sel]) pick(hits[sel].ticker);
    else if (e.key === "Escape") { box.hidden = true; input.blur(); }
  });
  input.addEventListener("blur", () => setTimeout(() => (box.hidden = true), 120));
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== input && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); input.focus(); }
  });
}

async function start() {
  view.innerHTML = '<div class="notice">Loading the board…</div>';
  const [board, universe, record, scorecard] = await Promise.all([
    loadJSON("data/board.json"), loadJSON("data/universe.json"), loadJSON("data/record.json"), loadJSON("data/scorecard.json"),
  ]);
  Object.assign(data, { board, universe, record, scorecard });
  game.onChange(() => game.renderPlayer($("#player")));
  game.renderPlayer($("#player"));
  renderStatus();
  wireSearch();
  render();
  game.checkIn();
}

window.addEventListener("hashchange", () => { render(); view.focus({ preventScroll: true }); window.scrollTo(0, 0); });
start();
