// A tiny Excel (.xlsx) reader that runs entirely in the browser, with no
// outside libraries touching your financial file.
// An .xlsx file is a zip of XML files. We unzip just the parts we need with
// the browser's built-in DecompressionStream, then read the first sheet.

const u16 = (v, o) => v.getUint16(o, true);
const u32 = (v, o) => v.getUint32(o, true);

async function inflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

// Returns { "path/in/zip": Uint8Array } for the files we ask for (by test fn).
async function unzip(buffer, want) {
  const view = new DataView(buffer), bytes = new Uint8Array(buffer);
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 66000); i--) {
    if (u32(view, i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("That file isn't a valid .xlsx workbook.");
  const count = u16(view, eocd + 10);
  let p = u32(view, eocd + 16);
  const out = {}, decoder = new TextDecoder();
  for (let n = 0; n < count; n++) {
    if (u32(view, p) !== 0x02014b50) break;
    const method = u16(view, p + 10), size = u32(view, p + 20);
    const nameLen = u16(view, p + 28), extraLen = u16(view, p + 30), commentLen = u16(view, p + 32);
    const local = u32(view, p + 42);
    const name = decoder.decode(bytes.subarray(p + 46, p + 46 + nameLen));
    if (want(name)) {
      const start = local + 30 + u16(view, local + 26) + u16(view, local + 28);
      const data = bytes.subarray(start, start + size);
      out[name] = method === 0 ? data : await inflate(data);
    }
    p += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}

const xml = (data) => new DOMParser().parseFromString(new TextDecoder().decode(data), "application/xml");
const all = (node, tag) => [...node.getElementsByTagNameNS("*", tag)];
const colIndex = (ref) => [...ref.replace(/\d+/g, "")].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1;

// Zip paths can come as "xl/..." or "/xl/...", in any letter case.
const norm = (p) => p.replace(/\\/g, "/").replace(/^\/+/, "").toLowerCase();

// Resolve a relationship target ("worksheets/sheet1.xml" or "/xl/worksheets/x.xml") against xl/.
function resolve(target) {
  const t = target.replace(/\\/g, "/");
  if (t.startsWith("/")) return norm(t);
  const parts = ["xl"];
  for (const seg of t.split("/")) { if (seg === "..") parts.pop(); else if (seg && seg !== ".") parts.push(seg); }
  return norm(parts.join("/"));
}

// Finds the first sheet the proper way (workbook -> relationships), then falls
// back to any worksheet file. Questrade and other exporters name sheets differently.
function locateParts(files) {
  const byNorm = Object.fromEntries(Object.entries(files).map(([k, v]) => [norm(k), v]));
  let sheet = null, shared = null;
  const wb = byNorm["xl/workbook.xml"], rels = byNorm["xl/_rels/workbook.xml.rels"];
  if (wb && rels) {
    const relMap = Object.fromEntries(all(xml(rels), "Relationship").map((r) =>
      [r.getAttribute("Id"), { target: r.getAttribute("Target") || "", type: r.getAttribute("Type") || "" }]));
    const first = all(xml(wb), "sheet")[0];
    const rid = first && [...first.attributes].find((a) => a.localName === "id")?.value;
    if (rid && relMap[rid]) sheet = byNorm[resolve(relMap[rid].target)] || null;
    const ss = Object.values(relMap).find((r) => /sharedStrings$/i.test(r.type));
    if (ss) shared = byNorm[resolve(ss.target)] || null;
  }
  if (!sheet) {
    const name = Object.keys(byNorm).filter((n) => /^xl\/worksheets\/[^/]+\.xml$/.test(n)).sort()[0];
    sheet = name ? byNorm[name] : null;
  }
  if (!shared) shared = byNorm[Object.keys(byNorm).find((n) => /sharedstrings[^/]*\.xml$/.test(n))] || null;
  return { sheet, shared, names: Object.keys(files) };
}

// First worksheet -> array of rows, each an array of cell strings.
export async function readXlsx(buffer) {
  const files = await unzip(buffer, (n) => /\.(xml|rels)$/i.test(n));
  const { sheet, shared: sharedXml, names } = locateParts(files);
  if (!sheet) {
    // Only the internal part names are shown (never your data), to help diagnose odd exports.
    throw new Error(`Couldn't find a worksheet in that file. Parts inside: ${names.slice(0, 12).join(", ") || "none"}. `
      + "Try opening it in Excel and using Save As → CSV UTF-8.");
  }
  const shared = sharedXml ? all(xml(sharedXml), "si").map((si) => all(si, "t").map((t) => t.textContent).join("")) : [];
  const rows = [];
  for (const row of all(xml(sheet), "row")) {
    const cells = [];
    for (const c of all(row, "c")) {
      const type = c.getAttribute("t"), v = all(c, "v")[0]?.textContent ?? "";
      let value;
      if (type === "s") value = shared[+v] ?? "";
      else if (type === "inlineStr") value = all(c, "t").map((t) => t.textContent).join("");
      else if (type === "b") value = v === "1" ? "TRUE" : "FALSE";
      else value = v;
      const ref = c.getAttribute("r");
      cells[ref ? colIndex(ref) : cells.length] = value;
    }
    rows.push(Array.from(cells, (x) => x ?? ""));
  }
  return rows.filter((r) => r.some((x) => String(x).trim()));
}
