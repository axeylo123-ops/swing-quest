// The Portfolio tab: import a Questrade CSV IN THE BROWSER ONLY.
// The file is read locally with FileReader; nothing is uploaded or sent anywhere.
// Any column whose header mentions "account" is dropped before anything else
// looks at the data, and only symbol/quantity/cost/value are kept.
import { esc, price, dollars, pct, storage } from "./util.js";
import * as game from "./game.js";

const KEY = "sq.portfolio.v1";
const CANADIAN = /\.(TO|V|CN|NE|TSX|TSXV)$/i;

// ---- CSV parsing (handles quotes, commas inside quotes, CRLF) ----
export function parseCSV(text) {
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') q = false;
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((x) => x.trim()));
}

const num = (s) => {
  if (s == null) return null;
  let t = String(s).trim().replace(/[$,\s]/g, "");
  const neg = /^\(.*\)$/.test(t);
  t = t.replace(/[()]/g, "");
  const v = parseFloat(t);
  return Number.isFinite(v) ? (neg ? -v : v) : null;
};

const FIELDS = {
  symbol: /^(symbol|ticker|security symbol)$|symbol/i,
  name: /description|security name|^name$/i,
  qty: /^(quantity|qty|shares|open qty|open quantity)$|quantity/i,
  avgCost: /average (cost|price)|avg\.? (cost|price)|cost per share|^average$/i,
  price: /current price|last price|market price|^price$/i,
  value: /market value|current market value/i,
  currency: /currency/i,
};

export function holdingsFromCSV(text) {
  const rows = parseCSV(text);
  const headerAt = rows.findIndex((r) => r.some((c) => FIELDS.symbol.test(c.trim())));
  if (headerAt < 0) throw new Error("Couldn't find a Symbol column. Export your Positions from Questrade as CSV.");
  // Drop account columns FIRST, by position, so no later code can read them.
  const header = rows[headerAt].map((h) => h.trim());
  const keep = header.map((h, i) => (/account/i.test(h) ? -1 : i)).filter((i) => i >= 0);
  const cols = {};
  for (const [field, re] of Object.entries(FIELDS)) {
    const i = keep.find((k) => re.test(header[k]) && !Object.values(cols).includes(k));
    if (i !== undefined) cols[field] = i;
  }
  if (cols.qty === undefined) throw new Error("Couldn't find a Quantity column.");

  const merged = new Map();
  for (const r of rows.slice(headerAt + 1)) {
    const raw = (r[cols.symbol] || "").trim().toUpperCase();
    if (!raw || /^total/i.test(raw)) continue;
    const canadian = CANADIAN.test(raw);
    const symbol = canadian ? raw : raw.replace(/\.US$/, "").replace(".", "-");
    const qty = num(r[cols.qty]);
    if (!qty) continue;
    const h = merged.get(symbol) || { symbol, name: "", qty: 0, cost: 0, value: 0, price: null, currency: "", market: canadian ? "CA" : "US" };
    const avg = cols.avgCost !== undefined ? num(r[cols.avgCost]) : null;
    const px = cols.price !== undefined ? num(r[cols.price]) : null;
    const val = cols.value !== undefined ? num(r[cols.value]) : (px != null ? px * qty : null);
    h.name = h.name || (cols.name !== undefined ? r[cols.name].trim() : "");
    h.qty += qty;
    if (avg != null) h.cost += avg * qty;  // same symbol in two accounts: combine
    if (val != null) h.value += val;
    if (px != null) h.price = px;
    if (cols.currency !== undefined) h.currency = r[cols.currency].trim();
    merged.set(symbol, h);
  }
  return [...merged.values()].map((h) => ({
    symbol: h.symbol, name: h.name, qty: h.qty, avgCost: h.cost ? h.cost / h.qty : null,
    price: h.price, value: h.value || null, currency: h.currency, market: h.market,
  }));
}

// ---- matching holdings to signals ----
function signalFor(h, today, live) {
  if (h.market === "CA") return { cls: "", text: "No signal coverage (Canadian listing)" };
  const pick = today?.picks?.find((p) => p.ticker === h.symbol);
  if (pick) return { cls: "ready", text: `Today's pick · score ${pick.score}`, plan: pick.plan };
  const open = live?.open?.find((s) => s.ticker === h.symbol);
  if (open) return { cls: "ready", text: `Open signal from ${open.signal_date}`, plan: open.plan };
  const watch = today?.watchlist?.find((p) => p.ticker === h.symbol);
  if (watch) return { cls: "wait", text: `Watchlist · score ${watch.score} (${watch.timing})` };
  const skip = today?.skipped?.find((s) => s.ticker === h.symbol);
  if (skip) return { cls: "", text: `Insiders bought recently, but ${skip.reason}` };
  return { cls: "", text: "No current signal" };
}

export function renderPortfolio(view, today, live) {
  const saved = storage.get(KEY, null);
  const holdings = saved?.holdings || [];
  const rows = holdings.map((h) => ({ h, s: signalFor(h, today, live) }));
  const withSignal = rows.filter((r) => r.s.cls).length;
  const notOwned = (today?.picks || []).filter((p) => !holdings.some((h) => h.symbol === p.ticker));
  const total = holdings.reduce((a, h) => a + (h.value || 0), 0);

  view.innerHTML = `<div class="stack">
    <div class="panel hero">
      <div class="big">Your portfolio vs signals</div>
      <p>Import a Questrade positions CSV. It is read <strong>only in this browser</strong>, never uploaded,
        and account numbers are thrown away the moment the file is read.</p>
    </div>

    <label class="panel dropzone" id="drop">
      <input type="file" id="csv" accept=".csv,text/csv" hidden>
      <strong>${holdings.length ? "Import a newer CSV" : "Choose your Questrade CSV"}</strong>
      <div class="muted small">or drag and drop it here · Questrade → Accounts → Positions → Export to CSV</div>
    </label>
    <p id="csv-msg" class="small muted" role="status"></p>

    ${holdings.length ? `
    <div class="tiles">
      <div class="tile"><div class="label">Holdings</div><div class="value">${holdings.length}</div><div class="sub">imported ${esc(new Date(saved.importedAt).toLocaleDateString())}</div></div>
      <div class="tile"><div class="label">Market value</div><div class="value">${dollars(total)}</div><div class="sub">from your CSV</div></div>
      <div class="tile"><div class="label">With a signal</div><div class="value">${withSignal}</div><div class="sub">pick or watchlist</div></div>
    </div>
    <div class="panel table-wrap"><table>
      <thead><tr><th>Symbol</th><th class="num">Shares</th><th class="num">Avg cost</th><th class="num">Value</th><th>Signal</th></tr></thead>
      <tbody>${rows.map(({ h, s }) => `<tr>
        <td><strong>${esc(h.symbol)}</strong><div class="muted small">${esc(h.name)}</div></td>
        <td class="num">${h.qty}</td><td class="num">${price(h.avgCost)}</td><td class="num">${dollars(h.value)}</td>
        <td>${s.cls ? `<span class="chip ${s.cls}">${esc(s.text)}</span>` : `<span class="muted small">${esc(s.text)}</span>`}
          ${s.plan ? `<div class="small muted">stop ${price(s.plan.stop)} · target ${price(s.plan.target)}${h.price ? ` · now ${pct(h.price / s.plan.stop - 1)} above stop` : ""}</div>` : ""}</td>
      </tr>`).join("")}</tbody></table></div>
    ${notOwned.length ? `<div class="panel"><h3>Today's picks you don't own</h3>
      <p class="muted small" style="margin:4px 0 0">${notOwned.map((p) => `<strong>${esc(p.ticker)}</strong> (score ${p.score})`).join(" · ")}</p></div>` : ""}
    <button class="btn" id="clear">Remove portfolio from this browser</button>` : ""}
  </div>`;

  const input = view.querySelector("#csv"), drop = view.querySelector("#drop"), msg = view.querySelector("#csv-msg");
  const load = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = holdingsFromCSV(String(reader.result));
        if (!parsed.length) throw new Error("No positions found in that file.");
        storage.set(KEY, { importedAt: new Date().toISOString(), holdings: parsed });
        game.setFlag("portfolio");
        renderPortfolio(view, today, live);
        game.toast("Portfolio imported", `${parsed.length} holdings, saved only in this browser`);
      } catch (e) { msg.textContent = e.message; }
    };
    reader.readAsText(file);
  };
  input.addEventListener("change", () => load(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); load(e.dataTransfer.files[0]); });
  view.querySelector("#clear")?.addEventListener("click", () => { storage.remove(KEY); renderPortfolio(view, today, live); });
}
