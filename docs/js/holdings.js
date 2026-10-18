// Holdings: import your Questrade file (browser-only), set your risk rules,
// and see every holding judged by the same pillars as the top ideas.
import { esc, storage, dollars, price, getRules, setRules } from "./util.js";
import { holdingsFromFile } from "./portfolio.js";
import { chip, pct, cls, money, meters } from "./ui.js";
import * as game from "./game.js";

const KEY = "sq.portfolio.v1";

export function renderHoldings(view, universe, open) {
  const saved = storage.get(KEY, null);
  const holdings = saved?.holdings || [];
  const meta = saved?.meta;
  const rules = getRules();
  const by = Object.fromEntries((universe?.stocks || []).map((s) => [s.ticker, s]));
  const rows = holdings.map((h) => ({ h, s: by[h.symbol] }));
  const book = holdings.reduce((a, h) => a + (h.value ?? h.bookCost ?? (h.avgCost != null ? h.avgCost * h.qty : 0)), 0);

  view.innerHTML = `<div class="stack">
    <div class="section-head"><h2>Your holdings</h2><span class="tiny muted" title="Browser storage is shared by every page on this github.io address, so only publish your own pages there.">stored only in this browser · never uploaded</span></div>
    ${rows.length ? `<div class="hud"><div class="in">
      <div class="tiles" style="margin-bottom:12px">
        <div class="tile"><div class="k">Holdings</div><div class="v">${holdings.length}</div><div class="s">${rows.filter((r) => r.s).length} covered by the scanner</div></div>
        <div class="tile"><div class="k">${holdings.some((h) => h.value) ? "Market value" : "Book cost"}</div><div class="v">${dollars(book)}</div><div class="s">from your file</div></div>
        <div class="tile"><div class="k">Need a look</div><div class="v">${rows.filter((r) => r.s && ["Review", "Trim?"].includes(r.s.hold)).length}</div><div class="s">review or trim</div></div>
      </div>
      <div class="table-wrap"><table class="data"><thead><tr><th>Holding</th><th class="num">Shares</th><th class="num">Avg cost</th><th class="num">Now</th>
        <th class="num">Conv</th><th>Verdict</th><th>Why</th></tr></thead><tbody>
      ${rows.map(({ h, s }) => `<tr ${s ? `data-open="${esc(s.ticker)}" tabindex="0"` : ""}>
        <td><b>${esc(h.symbol)}</b> <span class="muted tiny">${esc((h.name || "").slice(0, 22))}</span></td>
        <td class="num">${h.qty}</td><td class="num">${price(h.avgCost)}</td>
        <td class="num ${s && h.avgCost ? cls(s.price / h.avgCost - 1) : ""}">${s ? `${s.price.toFixed(2)} <span class="tiny">${h.avgCost ? pct(s.price / h.avgCost - 1) : ""}</span>` : "–"}</td>
        <td class="num neon">${s ? Math.round(s.conviction) : "–"}</td>
        <td>${s ? chip(s.hold) : '<span class="chip ca">not covered</span>'}</td>
        <td class="tiny t2" style="white-space:normal;min-width:200px">${s ? esc(s.hold_why) : "Not in the ranked universe"}</td></tr>`).join("")}
      </tbody></table></div>
      ${meta?.source === "activity" ? `<p class="tiny muted" style="margin:10px 0 0">Rebuilt from trade history (${esc(meta.from || "?")} to ${esc(meta.to || "?")}). Correct only if the file
        covers every trade since you bought.${meta.oversold?.length ? ` Left out (sold more than bought in the file): ${meta.oversold.map(esc).join(", ")}.` : ""}</p>` : ""}
      <div class="row" style="margin-top:12px"><button class="btn" id="clear">Remove from this browser</button></div>
    </div></div>` : ""}

    <label class="hud hot dropzone-wrap" style="display:block"><div class="in dropzone" id="drop">
      <input type="file" id="file" accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden>
      <div style="font:700 16px var(--font-display);letter-spacing:.14em;text-transform:uppercase;color:var(--text)">${holdings.length ? "Import a newer file" : "Import your Questrade file"}</div>
      <div class="small">Excel (.xlsx) or CSV · positions or trade history both work · drag and drop or click</div>
    </div></label>
    <p id="msg" class="small" style="color:var(--warn);margin:0" role="status"></p>

    <div class="hud"><div class="in">
      <div class="section-head"><h2>Risk rules</h2></div>
      <p class="small t2" style="margin:0 0 10px">Used to size every trade so a stop-out costs only a fixed slice of your account.</p>
      <div class="row">
        <label class="tiny muted">ACCOUNT SIZE ($)<br><input class="field mono" id="acct" type="number" min="0" step="100" value="${rules.account ?? ""}" placeholder="10000"></label>
        <label class="tiny muted">RISK PER TRADE (%)<br><input class="field mono" id="risk" type="number" min="0.25" max="5" step="0.25" value="${rules.riskPct}"></label>
        <button class="btn primary" id="save" style="align-self:flex-end">Save</button>
      </div>
    </div></div>
  </div>`;

  const msg = view.querySelector("#msg");
  const load = async (file) => {
    if (!file) return;
    msg.textContent = "";
    try {
      const parsed = await holdingsFromFile(file);
      if (!parsed.length) throw new Error("No holdings found in that file.");
      storage.set(KEY, { importedAt: new Date().toISOString(), holdings: parsed, meta: parsed.meta || null });
      game.setFlag("portfolio");
      renderHoldings(view, universe, open);
      game.toast("Holdings linked", `${parsed.length} holdings, saved only in this browser`);
    } catch (e) { msg.textContent = e.message; }
  };
  const input = view.querySelector("#file"), drop = view.querySelector("#drop");
  input.addEventListener("change", () => load(input.files[0]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("drag"); load(e.dataTransfer.files[0]); });
  view.querySelector("#clear")?.addEventListener("click", () => { storage.remove(KEY); renderHoldings(view, universe, open); });
  view.querySelector("#save").addEventListener("click", () => {
    const account = parseFloat(view.querySelector("#acct").value), riskPct = parseFloat(view.querySelector("#risk").value);
    if (!(account > 0) || !(riskPct > 0) || riskPct > 5) { game.toast("Check the numbers", "Account above $0, risk 0.25% to 5%"); return; }
    setRules({ account, riskPct });
    game.toast("Risk rules saved", `${riskPct}% = ${dollars(account * riskPct / 100)} per trade`);
  });
  view.querySelectorAll("tr[data-open]").forEach((tr) => {
    tr.addEventListener("click", () => open(tr.dataset.open, tr));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(tr.dataset.open, tr); });
  });
}
