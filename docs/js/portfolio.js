// The Treasury (Portfolio) tab: import a Questrade positions file (Excel or CSV)
// IN THE BROWSER ONLY. The file is read locally; nothing is uploaded or sent anywhere.
// Any column whose header mentions "account" is dropped before anything else
// looks at the data, and only symbol/quantity/cost/value are kept.
import { esc, price, dollars, pct, storage, getRules, setRules } from "./util.js";
import * as game from "./game.js";
import { emblem } from "./art.js";
import { readXlsx } from "./xlsx.js";

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

// Activity / trade-history exports list every buy and sell, not what you hold now.
const ACTIVITY = /transaction date|settlement date|trade date|activity type|^action$/i;
export const WRONG_EXPORT = "This looks like your trade history (activities), not your current holdings. "
  + "In Questrade, open your account's Positions (holdings) page and use its export button, then bring that file here.";

export const holdingsFromCSV = (text) => holdingsFromRows(parseCSV(text));

// Excel (.xlsx) or CSV, decided by the file's first bytes ("PK" = zip = xlsx).
export async function holdingsFromFile(file) {
  const buf = await file.arrayBuffer();
  const head = new Uint8Array(buf.slice(0, 8));
  if (head[0] === 0x50 && head[1] === 0x4b) return holdingsFromRows(await readXlsx(buf));
  if (head[0] === 0xd0 && head[1] === 0xcf) {
    throw new Error("That's an old-style Excel file (.xls). Open it in Excel and use Save As → Excel Workbook (.xlsx) or CSV.");
  }
  return holdingsFromCSV(new TextDecoder().decode(buf));
}

export function holdingsFromRows(rawRows) {
  const rows = rawRows.map((r) => r.map((c) => String(c ?? "")));
  const headerAt = rows.findIndex((r) => r.some((c) => FIELDS.symbol.test(c.trim())));
  if (headerAt < 0) throw new Error("Couldn't find a Symbol column. Export your Positions from Questrade (CSV or Excel).");
  // Drop account columns FIRST, by position, so no later code can read them.
  const header = rows[headerAt].map((h) => h.trim());
  if (header.some((h) => ACTIVITY.test(h))) throw new Error(WRONG_EXPORT);
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
    h.name = h.name || (cols.name !== undefined ? (r[cols.name] || "").trim() : "");
    h.qty += qty;
    if (avg != null) h.cost += avg * qty;  // same symbol in two accounts: combine
    if (val != null) h.value += val;
    if (px != null) h.price = px;
    if (cols.currency !== undefined) h.currency = (r[cols.currency] || "").trim();
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
  if (pick) return { cls: "open", text: `Tonight's quest · ${pick.score}`, plan: pick.plan };
  const open = live?.open?.find((s) => s.ticker === h.symbol);
  if (open) return { cls: "open", text: `Open quest since ${open.signal_date}`, plan: open.plan };
  const watch = today?.watchlist?.find((p) => p.ticker === h.symbol);
  if (watch) return { cls: "blocked", text: `Rumor · ${watch.score} (path ${watch.timing === "Wait" ? "blocked" : "fled"})` };
  const skip = today?.skipped?.find((s) => s.ticker === h.symbol);
  if (skip) return { cls: "", text: `Insiders bought recently, but ${skip.reason}` };
  return { cls: "", text: "No current signal" };
}

export function renderPortfolio(view, today, live) {
  const saved = storage.get(KEY, null);
  const rules = getRules();
  const holdings = saved?.holdings || [];
  const rows = holdings.map((h) => ({ h, s: signalFor(h, today, live) }));
  const withSignal = rows.filter((r) => r.s.cls).length;
  const notOwned = (today?.picks || []).filter((p) => !holdings.some((h) => h.symbol === p.ticker));
  const total = holdings.reduce((a, h) => a + (h.value || 0), 0);

  view.innerHTML = `<div class="stack">
    <div class="panel framed hero-panel">
      <div class="kicker">The Treasury</div>
      <div class="big">Your holdings vs the quests</div>
      <p>Bring your Questrade positions file (Excel or CSV). It is read <strong>only in this browser</strong>, never uploaded,
        and account numbers are burned the moment the file is opened.</p>
    </div>

    <div class="panel framed on-dark">
      <h3>Your trading rules</h3>
      <p class="small muted" style="margin:4px 0 10px">Used to tell you how many shares to buy on each quest, so a hit retreat (stop-loss)
        only costs a small, fixed slice of your account. Saved only in this browser.</p>
      <div class="row">
        <label class="small">Account size ($)<br><input id="acct" type="number" min="0" step="100" inputmode="decimal"
          value="${rules.account ?? ""}" placeholder="e.g. 10000" class="field"></label>
        <label class="small">Risk per quest (%)<br><input id="riskpct" type="number" min="0.25" max="5" step="0.25" inputmode="decimal"
          value="${rules.riskPct}" class="field"></label>
        <button class="btn gold" id="save-rules" style="align-self:flex-end">Save rules</button>
      </div>
      <p class="small muted" style="margin:8px 0 0">Common practice is to risk 0.5–2% per trade. With 1% on a $10,000 account, a stopped-out quest costs about $100.
        Use the currency you'll trade in (for US stocks in a CAD account, convert first).</p>
    </div>

    <label class="panel dropzone" id="drop">
      <input type="file" id="csv" accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden>
      ${emblem("key", 46)}
      <div class="display" style="color:var(--gold-bright);font-size:17px;margin-top:6px">${holdings.length ? "Bring a newer ledger" : "Open the vault: choose your Questrade positions file"}</div>
      <div class="muted small">Excel (.xlsx) or CSV · or drag and drop it here · use the export on your account's Positions page, not History</div>
    </label>
    <p id="csv-msg" class="small" style="color:var(--amber)" role="status"></p>

    ${holdings.length ? `
    <div class="panel framed on-dark">
      <div class="tallies" style="margin-top:0">
        <div class="tally"><div class="v">${holdings.length}</div><div class="k">Holdings</div><div class="s">imported ${esc(new Date(saved.importedAt).toLocaleDateString())}</div></div>
        <div class="tally"><div class="v">${dollars(total)}</div><div class="k">Market value</div><div class="s">from your file</div></div>
        <div class="tally"><div class="v">${withSignal}</div><div class="k">On the board</div><div class="s">quest or rumor</div></div>
      </div>
      <div class="table-wrap" style="margin-top:14px"><table>
        <thead><tr><th>Holding</th><th class="num">Shares</th><th class="num">Avg cost</th><th class="num">Value</th><th>On the board?</th></tr></thead>
        <tbody>${rows.map(({ h, s }) => `<tr>
          <td><strong>${esc(h.symbol)}</strong><div class="muted small">${esc(h.name)}</div></td>
          <td class="num">${h.qty}</td><td class="num">${price(h.avgCost)}</td><td class="num">${dollars(h.value)}</td>
          <td>${s.cls ? `<span class="chip ${s.cls} dark">${esc(s.text)}</span>` : `<span class="muted small">${esc(s.text)}</span>`}
            ${s.plan ? `<div class="small muted">retreat ${price(s.plan.stop)} · treasure ${price(s.plan.target)}${h.price ? ` · now ${pct(h.price / s.plan.stop - 1)} above the retreat` : ""}</div>` : ""}</td>
        </tr>`).join("")}</tbody></table></div>
    </div>
    ${notOwned.length ? `<div class="panel on-dark"><h3>Tonight's quests you don't hold</h3>
      <p class="small" style="margin:6px 0 0">${notOwned.map((p) => `<strong>${esc(p.ticker)}</strong> <span class="muted">(${p.score})</span>`).join(" · ")}</p></div>` : ""}
    <div class="center"><button class="btn" id="clear">Remove portfolio from this browser</button></div>` : ""}
  </div>`;

  const input = view.querySelector("#csv"), drop = view.querySelector("#drop"), msg = view.querySelector("#csv-msg");
  const load = async (file) => {
    if (!file) return;
    msg.textContent = "";
    try {
      const parsed = await holdingsFromFile(file);
      if (!parsed.length) throw new Error("No positions found in that file.");
      storage.set(KEY, { importedAt: new Date().toISOString(), holdings: parsed });
      game.setFlag("portfolio");
      renderPortfolio(view, today, live);
      game.toast("Portfolio imported", `${parsed.length} holdings, saved only in this browser`);
    } catch (e) { msg.textContent = e.message; }
  };
  input.addEventListener("change", () => load(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); load(e.dataTransfer.files[0]); });
  view.querySelector("#clear")?.addEventListener("click", () => { storage.remove(KEY); renderPortfolio(view, today, live); });
  view.querySelector("#save-rules").addEventListener("click", () => {
    const account = parseFloat(view.querySelector("#acct").value), riskPct = parseFloat(view.querySelector("#riskpct").value);
    if (!(account > 0) || !(riskPct > 0) || riskPct > 5) { game.toast("Check your rules", "Account above $0, risk between 0.25% and 5%"); return; }
    setRules({ account, riskPct });
    game.toast("Rules saved", `Risking ${riskPct}% (${dollars(account * riskPct / 100)}) per quest`);
  });
}
