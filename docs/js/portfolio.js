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

// Activity / trade-history exports list every buy and sell. We rebuild holdings from them.
const ACTIVITY = /transaction date|settlement date|trade date|activity type|^action$/i;
const ACT_FIELDS = {
  date: /transaction date|trade date|^date$/i, action: /^action$/i, type: /activity type/i,
  symbol: /symbol/i, name: /description/i, qty: /quantity/i, price: /^price$/i,
  commission: /commission/i, gross: /gross amount/i, currency: /currency/i,
};
const SYMBOL_OK = /^[A-Z][A-Z0-9.\-]{0,9}$/;

// Excel stores dates as day counts since 1899-12-30; text dates come in many shapes.
function dayValue(v) {
  const s = String(v ?? "").trim();
  if (/^\d{4,6}(\.\d+)?$/.test(s)) return parseFloat(s);
  const iso = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  const t = iso ? Date.UTC(+iso[1], +iso[2] - 1, +iso[3]) : Date.parse(s);
  return Number.isFinite(t) ? t / 86400000 + 25569 : null;
}
const dayLabel = (d) => (d == null ? null : new Date((d - 25569) * 86400000).toISOString().slice(0, 10));

/* Rebuild what you hold from a trade-history file: buys add shares, sells
   remove them, and average cost follows Canada's adjusted cost base method
   (commissions included). Only correct if the file covers every trade since
   you bought what you still own. */
function holdingsFromActivity(rows, headerAt, header, keep) {
  const cols = {};
  for (const [field, re] of Object.entries(ACT_FIELDS)) {
    const i = keep.find((k) => re.test(header[k]) && !Object.values(cols).includes(k));
    if (i !== undefined) cols[field] = i;
  }
  if (cols.symbol === undefined || cols.qty === undefined) throw new Error("This trade history has no Symbol or Quantity column.");
  const cell = (r, f) => (cols[f] === undefined ? "" : String(r[cols[f]] ?? "").trim());

  const trades = [];
  rows.slice(headerAt + 1).forEach((r, order) => {
    const raw = cell(r, "symbol").toUpperCase(), action = cell(r, "action"), type = cell(r, "type");
    const qty = num(cell(r, "qty"));
    if (!raw || !qty || !SYMBOL_OK.test(raw)) return;
    const isTrade = /trade/i.test(type) || (!type && /^(buy|sell)/i.test(action));
    const isTransfer = /transfer/i.test(type);
    if (!isTrade && !isTransfer) return;              // dividends, deposits, fees, interest...
    let shares = Math.abs(qty);
    if (/^sell/i.test(action)) shares = -shares;
    else if (!/^buy/i.test(action)) shares = qty;     // transfers etc.: trust the sign in the file
    let px = num(cell(r, "price"));
    const gross = num(cell(r, "gross"));
    if (!px && gross) px = Math.abs(gross / qty);
    trades.push({ raw, shares, price: px || 0, fee: Math.abs(num(cell(r, "commission")) || 0),
      day: dayValue(cell(r, "date")), order, name: cell(r, "name"), currency: cell(r, "currency") });
  });
  // Oldest first (exports are often newest first); keep file order for same-day trades.
  trades.sort((a, b) => (a.day ?? 0) - (b.day ?? 0) || b.order - a.order);

  const book = new Map(), oversold = new Set();
  for (const t of trades) {
    const canadian = CANADIAN.test(t.raw);
    const symbol = canadian ? t.raw : t.raw.replace(/\.US$/, "").replace(".", "-");
    const h = book.get(symbol) || { symbol, name: t.name, qty: 0, cost: 0, currency: t.currency, market: canadian ? "CA" : "US" };
    if (t.shares > 0) { h.cost += t.shares * t.price + t.fee; h.qty += t.shares; }
    else {
      const sell = -t.shares;
      if (sell > h.qty + 1e-9) oversold.add(symbol);
      const avg = h.qty > 0 ? h.cost / h.qty : 0;
      h.qty = Math.max(0, h.qty - sell);
      h.cost = h.qty > 1e-9 ? Math.max(0, h.cost - avg * sell) : 0;
    }
    book.set(symbol, h);
  }
  const holdings = [...book.values()].filter((h) => h.qty > 1e-6).map((h) => ({
    symbol: h.symbol, name: h.name, qty: +h.qty.toFixed(6), avgCost: h.cost / h.qty, price: null, value: null,
    bookCost: h.cost, currency: h.currency, market: h.market,
  }));
  const days = trades.map((t) => t.day).filter((d) => d != null);
  holdings.meta = {
    source: "activity",
    from: dayLabel(days.length ? Math.min(...days) : null), to: dayLabel(days.length ? Math.max(...days) : null),
    trades: trades.length, oversold: [...oversold],
  };
  return holdings;
}

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
  const keep = header.map((h, i) => (/account/i.test(h) ? -1 : i)).filter((i) => i >= 0);
  if (header.some((h) => ACTIVITY.test(h))) return holdingsFromActivity(rows, headerAt, header, keep);
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

// Briefs come from a command you run on your PC (they stay private, never published).
function briefPanel(holdings, briefs) {
  const cmd = `.venv\\Scripts\\python -m swingquest briefs ${holdings.map((h) => h.symbol).join(" ")}`;
  const missing = holdings.filter((h) => !briefs?.briefs?.[h.symbol]).length;
  return `<div style="margin-top:14px;border-top:1px solid var(--line);padding-top:12px">
    <h3>Holding briefs: analysts, trend, insiders</h3>
    <p class="small muted" style="margin:4px 0 8px">${briefs ? `Updated ${esc(new Date(briefs.generated_at).toLocaleString())}. ` : ""}${missing
      ? `${missing} holding${missing === 1 ? " has" : "s have"} no brief yet. ` : ""}To protect your privacy, briefs are made on your PC and never published.
      Copy this command, paste it into the terminal in the Swing Quest folder, then refresh this page:</p>
    <div class="row"><code id="brief-cmd" style="flex:1 1 220px;max-width:100%;overflow-x:auto;white-space:nowrap;padding:8px;display:block">${esc(cmd)}</code>
      <button class="btn" id="copy-cmd">Copy command</button></div>
    <p class="small muted" style="margin:6px 0 0">After the first run, the daily job on your PC refreshes them automatically.</p></div>`;
}

export function renderPortfolio(view, today, live, briefs = null) {
  const saved = storage.get(KEY, null);
  const rules = getRules();
  const holdings = saved?.holdings || [];
  const rows = holdings.map((h) => ({ h, s: signalFor(h, today, live) }));
  const withSignal = rows.filter((r) => r.s.cls).length;
  const notOwned = (today?.picks || []).filter((p) => !holdings.some((h) => h.symbol === p.ticker));
  const total = holdings.reduce((a, h) => a + (h.value || 0), 0);
  const bookTotal = holdings.reduce((a, h) => a + (h.bookCost || 0), 0);
  const meta = saved?.meta;

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
      <div class="muted small">Excel (.xlsx) or CSV · or drag and drop it here · a positions export or your trade history (activities) both work</div>
    </label>
    <p id="csv-msg" class="small" style="color:var(--amber)" role="status"></p>

    ${holdings.length ? `
    ${meta?.source === "activity" ? `<div class="panel on-dark" style="border-color:var(--gold-deep)">
      <h3>Rebuilt from your trade history</h3>
      <p class="small" style="margin:6px 0 0">${meta.trades} trades from ${esc(meta.from || "?")} to ${esc(meta.to || "?")}: buys add shares, sells remove them,
        and average cost follows Canada's adjusted cost base (fees included). This is only right if the file covers <strong>every trade since you
        bought</strong> what you still own. Check the share counts against Questrade.</p>
      ${meta.oversold?.length ? `<p class="small" style="margin:6px 0 0;color:var(--amber)">Sold more than bought in this file, so left out:
        ${meta.oversold.map(esc).join(", ")}. Export a longer date range to include them.</p>` : ""}</div>` : ""}
    <div class="panel framed on-dark">
      <div class="tallies" style="margin-top:0">
        <div class="tally"><div class="v">${holdings.length}</div><div class="k">Holdings</div><div class="s">imported ${esc(new Date(saved.importedAt).toLocaleDateString())}</div></div>
        <div class="tally"><div class="v">${dollars(total || bookTotal)}</div><div class="k">${total ? "Market value" : "Book cost"}</div><div class="s">${total ? "from your file" : "what you paid, incl. fees"}</div></div>
        <div class="tally"><div class="v">${withSignal}</div><div class="k">On the board</div><div class="s">quest or rumor</div></div>
      </div>
      <div class="table-wrap" style="margin-top:14px"><table>
        <thead><tr><th>Holding</th><th class="num">Shares</th><th class="num">Avg cost</th><th class="num">${total ? "Value" : "Book cost"}</th><th>On the board?</th></tr></thead>
        <tbody>${rows.map(({ h, s }) => `<tr>
          <td><strong>${esc(h.symbol)}</strong><div class="muted small">${esc(h.name)}</div></td>
          <td class="num">${h.qty}</td><td class="num">${price(h.avgCost)}</td><td class="num">${dollars(h.value ?? h.bookCost)}</td>
          <td>${s.cls ? `<span class="chip ${s.cls} dark">${esc(s.text)}</span>` : `<span class="muted small">${esc(s.text)}</span>`}
            ${s.plan ? `<div class="small muted">retreat ${price(s.plan.stop)} · treasure ${price(s.plan.target)}${h.price ? ` · now ${pct(h.price / s.plan.stop - 1)} above the retreat` : ""}</div>` : ""}</td>
        </tr>${briefs?.briefs?.[h.symbol] ? `<tr><td colspan="5" class="small" style="color:var(--text-2);padding-top:0">
          <em>${esc(briefs.briefs[h.symbol].text)}</em></td></tr>` : ""}`).join("")}</tbody></table></div>
      ${briefPanel(holdings, briefs)}
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
      storage.set(KEY, { importedAt: new Date().toISOString(), holdings: parsed, meta: parsed.meta || null });
      game.setFlag("portfolio");
      renderPortfolio(view, today, live, briefs);
      game.toast("Portfolio imported", `${parsed.length} holdings, saved only in this browser`);
    } catch (e) { msg.textContent = e.message; }
  };
  input.addEventListener("change", () => load(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); load(e.dataTransfer.files[0]); });
  view.querySelector("#clear")?.addEventListener("click", () => { storage.remove(KEY); renderPortfolio(view, today, live, briefs); });
  view.querySelector("#copy-cmd")?.addEventListener("click", async () => {
    const text = view.querySelector("#brief-cmd").textContent;
    try { await navigator.clipboard.writeText(text); game.toast("Command copied", "Paste it into the terminal in the Swing Quest folder"); }
    catch { game.toast("Couldn't copy", "Select the command and copy it by hand"); }
  });
  view.querySelector("#save-rules").addEventListener("click", () => {
    const account = parseFloat(view.querySelector("#acct").value), riskPct = parseFloat(view.querySelector("#riskpct").value);
    if (!(account > 0) || !(riskPct > 0) || riskPct > 5) { game.toast("Check your rules", "Account above $0, risk between 0.25% and 5%"); return; }
    setRules({ account, riskPct });
    game.toast("Rules saved", `Risking ${riskPct}% (${dollars(account * riskPct / 100)}) per quest`);
  });
}
