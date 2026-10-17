// Swing Quest dashboard entry point: loads the data files, routes between tabs.
import { $, $$, loadJSON } from "./util.js";
import { banner } from "./art.js";
import * as fx from "./fx.js";
import * as game from "./game.js";
import { rows as historyRows } from "./history.js";
import { renderToday } from "./today.js";
import { renderScorecard } from "./scorecard.js";
import { renderHealth } from "./health.js";
import { renderPortfolio } from "./portfolio.js";

const data = {};
const view = $("#view");
const TABS = ["today", "scorecard", "health", "portfolio", "quests"];

function render() {
  const tab = TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "today";
  $$(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (tab === "today") renderToday(view, data.today, data.hist, data.live);
  else if (tab === "scorecard") renderScorecard(view, data.scorecard, data.hist);
  else if (tab === "health") renderHealth(view, data.health, data.scorecard, data.today);
  else if (tab === "portfolio") renderPortfolio(view, data.today, data.live);
  else game.renderHero(view);
}

async function start() {
  $("#banner").innerHTML = banner();
  fx.embers();
  view.innerHTML = '<div class="panel hero-panel"><div class="big">Unrolling the scrolls…</div></div>';
  const [today, scorecard, health, live, history] = await Promise.all([
    loadJSON("data/today.json"), loadJSON("data/scorecard.json"), loadJSON("data/health.json"),
    loadJSON("data/live.json"), loadJSON("data/history.json"),
  ]);
  Object.assign(data, { today, scorecard, health, live, hist: historyRows(history) });
  game.onChange(() => game.renderPlayer($("#player")));
  game.renderPlayer($("#player"));
  render();
  game.checkIn(today);
}

window.addEventListener("hashchange", () => { render(); view.focus({ preventScroll: true }); window.scrollTo(0, 0); });
let resizeTimer, lastWidth = innerWidth;
window.addEventListener("resize", () => {
  if (innerWidth === lastWidth) return;          // ignore mobile address-bar height changes
  lastWidth = innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (["today", "scorecard", ""].includes(location.hash.slice(1))) render(); }, 250);
});
start();
