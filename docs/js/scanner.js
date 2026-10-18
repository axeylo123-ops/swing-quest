// Scanner: every ranked stock. Filter, sort by any pillar, open any dossier.
import { esc } from "./util.js";
import { PILLARS, chip, pct, cls, headlineUpside } from "./ui.js";

const PAGE = 50;
const state = { sort: "conviction", dir: -1, country: "All", verdict: "All", sector: "All", q: "", page: 0 };

const COLS = [
  { key: "rank", label: "#", num: true, get: (s) => s.rank },
  { key: "ticker", label: "Stock", get: (s) => s.ticker },
  { key: "conviction", label: "Conv", num: true, get: (s) => s.conviction },
  { key: "upside_head", label: "To target", num: true, get: (s) => headlineUpside(s).value ?? -9 },
  ...PILLARS.map(([k, label]) => ({ key: k, label, num: true, get: (s) => s.pillars?.[k] ?? 0, pillar: true })),
  { key: "verdict", label: "Status", get: (s) => s.verdict },
  { key: "price", label: "Price", num: true, get: (s) => s.price },
];

function filtered(stocks) {
  const q = state.q.trim().toUpperCase();
  let list = stocks.filter((s) =>
    (state.country === "All" || s.country === state.country) &&
    (state.verdict === "All" || s.verdict === state.verdict) &&
    (state.sector === "All" || s.sector === state.sector) &&
    (!q || s.ticker.includes(q) || (s.name || "").toUpperCase().includes(q)));
  const col = COLS.find((c) => c.key === state.sort) || COLS[2];
  list = [...list].sort((a, b) => {
    const x = col.get(a), y = col.get(b);
    return (x > y ? 1 : x < y ? -1 : 0) * state.dir;
  });
  return list;
}

function tableHTML(list) {
  const pages = Math.max(1, Math.ceil(list.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  const rows = list.slice(state.page * PAGE, (state.page + 1) * PAGE);
  return `<div class="table-wrap"><table class="data"><thead><tr>${COLS.map((c) =>
      `<th class="sortable th-full ${c.num ? "num" : ""} ${state.sort === c.key ? "sorted" : ""}" data-sort="${c.key}" tabindex="0"
        aria-sort="${state.sort === c.key ? (state.dir < 0 ? "descending" : "ascending") : "none"}">${c.label}${state.sort === c.key ? (state.dir < 0 ? " ▼" : " ▲") : ""}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((s) => {
      const up = headlineUpside(s);
      return `<tr data-open="${esc(s.ticker)}" tabindex="0">
        <td class="num muted">${s.rank}</td>
        <td><b>${esc(s.ticker)}</b> <span class="muted tiny">${esc((s.name || "").slice(0, 24))}</span></td>
        <td class="num neon">${Math.round(s.conviction)}</td>
        <td class="num ${cls(up.value)}">${pct(up.value)}</td>
        ${PILLARS.map(([k]) => `<td class="num"><span class="mini"><i style="width:${s.pillars?.[k] ?? 0}%"></i></span>${Math.round(s.pillars?.[k] ?? 0)}</td>`).join("")}
        <td>${chip(s.verdict)}</td>
        <td class="num">${s.price?.toFixed(2) ?? "–"}</td></tr>`;
    }).join("")}</tbody></table></div>
    <div class="pager"><button class="btn" data-page="-1" ${state.page === 0 ? "disabled" : ""}>Prev</button>
      <span>Page ${state.page + 1} / ${pages}</span><button class="btn" data-page="1" ${state.page >= pages - 1 ? "disabled" : ""}>Next</button></div>`;
}

export function renderScanner(view, universe, open) {
  const stocks = universe?.stocks || [];
  const sectors = [...new Set(stocks.map((s) => s.sector).filter(Boolean))].sort();
  const verdicts = ["Buy candidate", "Neutral", "Watch", "Don't chase", "Limited upside", "Avoid"];
  view.innerHTML = `
  <div class="stack">
    <div class="section-head"><h2>Market scanner</h2><span class="tiny muted" id="sc-count"></span></div>
    <div class="filters">
      <div class="seg" data-f="country">${["All", "US", "CA"].map((c) => `<button aria-pressed="${state.country === c}" data-v="${c}">${c === "CA" ? "Canada" : c}</button>`).join("")}</div>
      <select class="field" data-f="verdict" aria-label="Status"><option>All</option>${verdicts.map((v) => `<option ${state.verdict === v ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select class="field" data-f="sector" aria-label="Sector"><option>All</option>${sectors.map((v) => `<option ${state.sector === v ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <input class="field" data-f="q" placeholder="Filter by ticker or name" aria-label="Filter by ticker or name" value="${esc(state.q)}">
    </div>
    <div class="hud"><div class="in" style="padding:6px 8px" id="sc-table"></div></div>
  </div>`;
  const box = view.querySelector("#sc-table"), count = view.querySelector("#sc-count");
  // only the table repaints when you filter, sort or page (the filters keep focus)
  const paint = () => {
    const list = filtered(stocks);
    count.textContent = `${list.length.toLocaleString()} of ${stocks.length.toLocaleString()} stocks · click a column to sort`;
    box.innerHTML = tableHTML(list);
  };
  const sortBy = (key) => {
    if (state.sort === key) state.dir *= -1; else { state.sort = key; state.dir = key === "ticker" || key === "rank" ? 1 : -1; }
    paint();
  };
  box.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]"), pg = e.target.closest("[data-page]"), tr = e.target.closest("tr[data-open]");
    if (th) sortBy(th.dataset.sort);
    else if (pg) { state.page += +pg.dataset.page; paint(); window.scrollTo(0, 0); }
    else if (tr) open(tr.dataset.open, tr);
  });
  box.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const th = e.target.closest("th[data-sort]"), tr = e.target.closest("tr[data-open]");
    if (th) sortBy(th.dataset.sort); else if (tr) open(tr.dataset.open, tr);
  });
  view.querySelectorAll(".seg[data-f] button").forEach((b) => b.addEventListener("click", () => {
    state[b.closest(".seg").dataset.f] = b.dataset.v; state.page = 0;
    b.closest(".seg").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    paint();
  }));
  view.querySelectorAll("select[data-f]").forEach((sel) => sel.addEventListener("change", () => { state[sel.dataset.f] = sel.value; state.page = 0; paint(); }));
  const q = view.querySelector('input[data-f="q"]');
  q.addEventListener("input", () => { state.q = q.value; state.page = 0; clearTimeout(q._t); q._t = setTimeout(paint, 150); });
  paint();
}
