// Swing Quest dashboard entry point: loads the data files, routes between tabs.
import { $, $$, loadJSON } from "./util.js";
import * as game from "./game.js";
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
  if (tab === "today") renderToday(view, data.today);
  else if (tab === "scorecard") renderScorecard(view, data.scorecard);
  else if (tab === "health") renderHealth(view, data.health, data.scorecard, data.today);
  else if (tab === "portfolio") renderPortfolio(view, data.today, data.live);
  else game.renderQuests(view);
}

async function start() {
  view.innerHTML = '<div class="panel empty"><div class="big">Loading…</div></div>';
  const [today, scorecard, health, live] = await Promise.all([
    loadJSON("data/today.json"), loadJSON("data/scorecard.json"),
    loadJSON("data/health.json"), loadJSON("data/live.json"),
  ]);
  Object.assign(data, { today, scorecard, health, live });
  game.onChange(() => game.renderPlayer($("#player")));
  game.renderPlayer($("#player"));
  render();
  game.checkIn(today);
}

window.addEventListener("hashchange", () => { render(); view.focus({ preventScroll: true }); window.scrollTo(0, 0); });
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (!["portfolio", "quests"].includes(location.hash.slice(1))) render(); }, 200);
});
start();
