// Questrade file import (Excel or CSV): positions or trade history,
// parsed IN THE BROWSER ONLY. The file is read locally; nothing is uploaded or sent anywhere.
// Any column whose header mentions "account" is dropped before anything else
// looks at the data, and only symbol/quantity/cost/value are kept.
import { readXlsx } from "./xlsx.js";

const KEY = "sq.portfolio.v1";
const CANADIAN = /\.(TO|VN|V|CN|NE|TSX|TSXV)$/i;
const SUFFIX = { TO: "TO", TSX: "TO", VN: "V", V: "V", TSXV: "V", CN: "CN", NE: "NE" };
// Questrade symbol -> the ticker the scanner uses: BBD.B.TO -> BBD-B.TO, XYZ.VN -> XYZ.V, BRK.B -> BRK-B
export function yahooSymbol(raw) {
  const s = raw.trim().toUpperCase(), m = s.match(/^(.*)\.(TO|VN|V|CN|NE|TSX|TSXV)$/);
  return m ? `${m[1].replace(/\./g, "-")}.${SUFFIX[m[2]]}` : s.replace(/\.US$/, "").replace(/\./g, "-");
}

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
    const symbol = yahooSymbol(t.raw);
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
    const symbol = yahooSymbol(raw);
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
