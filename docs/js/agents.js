// Agents: the crew that builds the board every night, replayed step by step,
// plus the review crew that audits the system and proposes improvements.
// Every number shown comes from data/agents.json (written by the real run).
import { esc, niceDate } from "./util.js";
import { calm } from "./fx.js";

// ---- pixel sprites: one 12x12 bot, with a different hat/gear per agent ----
const BASE = [
  "............", ".....aa.....", ".....kk.....", "..kkkkkkkk..",
  ".kbbbbbbbbk.", ".kbeebbeebk.", ".kbeebbeebk.", ".kbbbbbbbbk.",
  ".kbbmmmmbbk.", "..kkkkkkkk..", "...kbbbbk...", "..kbbbbbbk..",
];
const GEAR = {
  scout:   { 0: "...a....a...", 1: "....aaaa...." },                                     // radar dish
  feed:    { 1: "............", 2: "..hhhhhhhh..", 3: ".hkkkkkkkkh.", 4: "hkbbbbbbbbkh",
             5: "hkbeebbeebkh", 6: "hkbeebbeebkh" },                                      // headset
  insider: { 1: "...dddddd...", 2: ".dddddddddd." },                                     // detective hat
  analyst: { 5: ".kgeeggeegk.", 6: ".kgeeggeegk." },                                     // glasses
  ranker:  { 0: "............", 1: "..a.a..a.a..", 2: "..aaaaaaaa.." },                   // crown
  risk:    { 5: ".kbrrrrrrbk.", 6: ".kbbbbbbbbk." },                                     // red visor
  planner: { 1: "....yyyy....", 2: "..yyyyyyyy.." },                                     // hard hat
  keeper:  { 10: "...kbttbk..." },                                                       // bow tie
  code:    { 5: ".kbvvvvvvbk.", 6: ".kbbbbbbbbk." },                                     // scanner visor
  method:  { 5: ".kgeeggeegk.", 6: ".kgeeggeegk.", 1: "....aaaa....", 2: ".....kk....." },
  design:  { 1: "...pppp.....", 2: "..pppppppp.." },                                     // beret
};
const ACCENT = { scout: "#44d62c", feed: "#19c7ff", insider: "#ffb21e", analyst: "#b78cff", ranker: "#44d62c",
  risk: "#ff5c5c", planner: "#ffd23e", keeper: "#19c7ff", code: "#19c7ff", method: "#b78cff", design: "#ff7ad9" };

function sprite(id) {
  const rows = BASE.map((r, y) => GEAR[id]?.[y] ?? r), groups = {};
  rows.forEach((row, y) => [...row].forEach((c, x) => {
    if (c !== ".") (groups[c] ||= []).push(`<rect x="${x}" y="${y}" width="1" height="1"/>`);
  }));
  return `<svg class="bot" viewBox="0 0 12 12" shape-rendering="crispEdges" aria-hidden="true" style="--acc:${ACCENT[id] || "#44d62c"}">
    ${Object.entries(groups).map(([c, r]) => `<g class="px-${c}">${r.join("")}</g>`).join("")}</svg>`;
}

function station(a, i) {
  return `<article class="station" data-i="${i}" data-state="idle">
    <div class="st-head"><span class="led" aria-hidden="true"></span><span class="st-n">0${i + 1}</span>
      <b class="st-name">${esc(a.name)}</b><span class="st-time mono">${a.secs != null ? `${a.secs}s` : ""}</span></div>
    <div class="rig">${sprite(a.id)}<div class="screen" aria-hidden="true">${"<i></i>".repeat(7)}</div></div>
    <div class="st-job">${esc(a.job)}</div>
    <div class="st-stat mono">${esc(a.stat)}</div>
    <ul class="st-log">${a.lines.map((l) => `<li data-text="${esc(l)}"></li>`).join("")}</ul>
  </article>`;
}

function reviewer(r) {
  const fixed = r.findings.filter((f) => f.status === "fixed").length, n = r.findings.length;
  return `<article class="reviewer">
    <div class="rig small">${sprite(r.id)}</div>
    <div style="min-width:0">
      <div class="spread"><b>${esc(r.name)}</b><span class="tiny muted">last review ${esc(niceDate(r.last_run))}</span></div>
      <div class="tiny t2">${esc(r.job)}</div>
      <div class="fixbar" title="${fixed} of ${n} findings fixed"><i style="width:${n ? (fixed / n) * 100 : 0}%"></i></div>
      <div class="tiny"><span class="neon">${fixed} fixed</span> · <span class="${n - fixed ? "warn" : "muted"}">${n - fixed} open</span></div>
      <details><summary class="tiny">Findings</summary><ul class="findings">
        ${r.findings.map((f) => `<li class="${f.status}"><span>${f.status === "fixed" ? "✓" : "○"}</span>${esc(f.text)}</li>`).join("")}
      </ul></details>
    </div></article>`;
}

let timers = [];
const clear = () => { timers.forEach(clearTimeout); timers = []; };
const later = (fn, ms) => timers.push(setTimeout(fn, ms));

function typeLine(li, speed) {
  const text = li.dataset.text;
  if (!speed) { li.textContent = text; return; }
  let k = 0;
  const tick = () => { li.textContent = text.slice(0, ++k); if (k < text.length) later(tick, speed); };
  tick();
}

// Replays the run: each agent works in turn, logs its output, hands a packet down the bus.
function replay(root, agents) {
  clear();
  const st = [...root.querySelectorAll(".station")], nodes = [...root.querySelectorAll(".bus-node")];
  const packet = root.querySelector(".packet"), banner = root.querySelector(".run-done");
  const instant = calm();
  st.forEach((s) => { s.dataset.state = "idle"; s.querySelectorAll("li").forEach((li) => (li.textContent = "")); });
  nodes.forEach((n) => n.classList.remove("on", "now"));
  banner.classList.remove("show");
  if (instant) {
    st.forEach((s) => { s.dataset.state = "done"; s.querySelectorAll("li").forEach((li) => typeLine(li, 0)); });
    nodes.forEach((n) => n.classList.add("on"));
    packet.style.left = "100%"; banner.classList.add("show");
    return;
  }
  const STEP = 1250;
  agents.forEach((a, i) => {
    later(() => {
      st[i].dataset.state = "working";
      nodes[i].classList.add("on", "now");
      if (i > 0) nodes[i - 1].classList.remove("now");
      packet.style.left = `${(i / Math.max(1, agents.length - 1)) * 100}%`;
      st[i].querySelectorAll("li").forEach((li, k) => later(() => typeLine(li, 14), 180 + k * 330));
      if (matchMedia("(max-width: 760px)").matches) st[i].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, i * STEP);
    later(() => { st[i].dataset.state = "done"; }, i * STEP + STEP - 120);
  });
  later(() => { nodes.forEach((n) => n.classList.remove("now")); banner.classList.add("show"); }, agents.length * STEP);
}

export function renderAgents(view, crew, reviews) {
  clear();
  if (!crew?.agents?.length) {
    view.innerHTML = `<div class="notice">No run recorded yet. It appears after the next nightly run (or <code>python -m swingquest daily</code>).</div>`;
    return;
  }
  const a = crew.agents, total = a.reduce((t, x) => t + (x.secs || 0), 0);
  const props = reviews?.proposals || [];
  view.innerHTML = `<div class="stack agents-view">
    <div class="spread">
      <div><h1 style="font-size:26px;letter-spacing:.12em">The crew</h1>
        <div class="small muted">${a.length} agents build the board every weekday evening · this is a replay of the latest run
          (prices as of ${esc(niceDate(crew.as_of))}${crew.mode === "offline" ? ", offline run from cached data" : ""})</div></div>
      <button class="btn" id="replay" type="button">↻ Replay run</button>
    </div>
    <div class="hud"><div class="in">
      <div class="bus" role="list" aria-label="Pipeline order">
        <div class="bus-track"><div class="packet"></div></div>
        ${a.map((x, i) => `<div class="bus-node" role="listitem" style="left:${(i / Math.max(1, a.length - 1)) * 100}%"><i></i><span>${esc(x.name.split(" ")[0])}</span></div>`).join("")}
      </div>
      <div class="floor">${a.map(station).join("")}</div>
      <div class="run-done"><span class="led on"></span> Run complete · ${a.length} agents · ${total.toFixed(1)}s of work · board published</div>
    </div></div>

    <div class="section-head"><h2>Review crew</h2><span class="tiny muted">audits the code, the scoring and the dashboard · proposes improvements</span></div>
    ${reviews ? `<div class="reviewers">${reviews.reviewers.map(reviewer).join("")}</div>
    <div class="hud"><div class="in">
      <div class="section-head"><h2>Proposals</h2><span class="tiny muted">${esc(reviews.note)}</span></div>
      <div class="proposals">${props.map((p) => `<div class="proposal">
        <div class="spread"><b>${esc(p.title)}</b><span class="chip ${p.status === "shipped" ? "buy" : p.status === "proposed" ? "watch" : "chase"}">${esc(p.status)}</span></div>
        <div class="tiny t2">${esc(p.why)}</div><div class="tiny muted">from the ${esc(p.by)} reviewer</div></div>`).join("")}</div>
    </div></div>` : `<div class="notice">No reviews yet.</div>`}
  </div>`;
  const root = view.querySelector(".agents-view");
  view.querySelector("#replay").addEventListener("click", () => replay(root, a));
  replay(root, a);
}

export const stopAgents = clear;
