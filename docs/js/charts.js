// Hand-drawn SVG charts (no libraries). Every chart has a hover tooltip.
// Colors come from CSS tokens so the theme lives in one place (styles.css).
import { esc, pct, price, shortDate } from "./util.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const NS = 'xmlns="http://www.w3.org/2000/svg"';

function ticks(min, max, count = 4) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

// A bar with only its data end rounded (the end away from the baseline).
function bar(x, yBase, yEnd, w, r = 4) {
  const h = Math.abs(yEnd - yBase);
  r = Math.min(r, w / 2, h);
  if (yEnd <= yBase) { // grows upward
    return `M${x},${yBase} V${yEnd + r} Q${x},${yEnd} ${x + r},${yEnd} H${x + w - r} Q${x + w},${yEnd} ${x + w},${yEnd + r} V${yBase} Z`;
  }
  return `M${x},${yBase} V${yEnd - r} Q${x},${yEnd} ${x + r},${yEnd} H${x + w - r} Q${x + w},${yEnd} ${x + w},${yEnd - r} V${yBase} Z`;
}

function hbar(xBase, xEnd, y, h, r = 4) {
  const w = Math.abs(xEnd - xBase);
  r = Math.min(r, h / 2, w);
  if (xEnd >= xBase) {
    return `M${xBase},${y} H${xEnd - r} Q${xEnd},${y} ${xEnd},${y + r} V${y + h - r} Q${xEnd},${y + h} ${xEnd - r},${y + h} H${xBase} Z`;
  }
  return `M${xBase},${y} H${xEnd + r} Q${xEnd},${y} ${xEnd},${y + r} V${y + h - r} Q${xEnd},${y + h} ${xEnd + r},${y + h} H${xBase} Z`;
}

function tooltip(el) {
  let tip = el.querySelector(".tooltip");
  if (!tip) { tip = document.createElement("div"); tip.className = "tooltip"; el.appendChild(tip); }
  return {
    show(html, x, y) { tip.innerHTML = html; tip.style.left = `${x}px`; tip.style.top = `${y}px`; tip.classList.add("show"); },
    hide() { tip.classList.remove("show"); },
  };
}

// ---------------------------------------------------------------------------
// Price chart: close line, 20-day average, buy zone band, stop & target lines.
export function priceChart(el, rows, plan) {
  if (!rows?.length) { el.innerHTML = '<p class="muted small">No chart data.</p>'; return; }
  const W = Math.max(280, el.clientWidth), H = 210;
  const m = { t: 12, r: 78, b: 22, l: 42 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const closes = rows.map((r) => r[4]);
  const lo = Math.min(...rows.map((r) => r[3]), plan?.stop ?? Infinity);
  const hi = Math.max(...rows.map((r) => r[2]), plan?.target ?? -Infinity);
  const pad = (hi - lo) * 0.06;
  const y0 = lo - pad, y1 = hi + pad;
  const x = (i) => m.l + (i * iw) / (rows.length - 1);
  const y = (v) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;

  const s1 = css("--series-1"), muted = css("--muted"), good = css("--good"), crit = css("--critical");
  // SVG path through the values; a missing value (null) lifts the pen.
  const path = (vals) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += `${pen ? " L" : " M"}${x(i)},${y(v)}`;
      pen = true;
    });
    return d.trim();
  };

  const yt = ticks(y0, y1, 4);
  const months = [];
  rows.forEach((r, i) => { if (i === 0 || r[0].slice(5, 7) !== rows[i - 1][0].slice(5, 7)) months.push(i); });

  let svg = `<svg ${NS} viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Price chart with buy zone, stop and target">`;
  svg += `<g class="grid">${yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>`).join("")}</g>`;
  svg += yt.map((v) => `<text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(v < 10 ? 2 : 0)}</text>`).join("");
  svg += months.slice(1).map((i) => `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${shortDate(rows[i][0]).split(" ")[0]}</text>`).join("");
  if (plan) {
    const zt = y(plan.entry_high), zb = y(plan.entry_low);
    svg += `<rect x="${m.l}" y="${zt}" width="${iw}" height="${Math.max(2, zb - zt)}" fill="var(--zone)"/>`;
    svg += `<text x="${m.l + 6}" y="${zt - 4}" style="fill:var(--text-2)">Buy zone</text>`;
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(plan.target)}" y2="${y(plan.target)}" stroke="${good}" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(plan.stop)}" y2="${y(plan.stop)}" stroke="${crit}" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    svg += `<text x="${W - m.r + 6}" y="${y(plan.target) + 4}" style="fill:var(--good-text)">Target ${plan.target.toFixed(2)}</text>`;
    svg += `<text x="${W - m.r + 6}" y="${y(plan.stop) + 4}" style="fill:var(--critical-text)">Stop ${plan.stop.toFixed(2)}</text>`;
  }
  svg += `<path d="${path(rows.map((r) => r[5]))}" fill="none" stroke="${muted}" stroke-width="1.5" stroke-dasharray="3 3"/>`;
  svg += `<path d="${path(closes)}" fill="none" stroke="${s1}" stroke-width="2" stroke-linejoin="round"/>`;
  svg += `<g class="hover" style="display:none"><line y1="${m.t}" y2="${m.t + ih}" stroke="${muted}" stroke-width="1"/>`
       + `<circle r="4.5" fill="${s1}" stroke="var(--panel)" stroke-width="2"/></g>`;
  svg += `<rect class="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent"/></svg>`;

  el.innerHTML = `<div class="legend"><span><i style="background:${s1}"></i>Price (close)</span>`
    + `<span><i style="background:${muted}"></i>20-day average</span></div>${svg}`;
  const tip = tooltip(el);
  const hover = el.querySelector(".hover"), hit = el.querySelector(".hit");
  const svgEl = el.querySelector("svg");
  const move = (ev) => {
    const box = svgEl.getBoundingClientRect();
    const px = ((ev.clientX - box.left) / box.width) * W;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round(((px - m.l) / iw) * (rows.length - 1))));
    const r = rows[i];
    hover.style.display = "";
    hover.querySelector("line").setAttribute("x1", x(i)); hover.querySelector("line").setAttribute("x2", x(i));
    hover.querySelector("circle").setAttribute("cx", x(i)); hover.querySelector("circle").setAttribute("cy", y(r[4]));
    const scale = box.width / W;
    tip.show(`<strong>${esc(shortDate(r[0]))}</strong><br>Close ${price(r[4])}`
      + (r[5] ? `<br><span class="t-muted">20-day avg ${price(r[5])}</span>` : ""),
      x(i) * scale, (y(r[4]) - 8) * scale + (box.top - el.getBoundingClientRect().top));
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", () => { hover.style.display = "none"; tip.hide(); });
}

// ---------------------------------------------------------------------------
// Vertical bars around a zero line. Positive = blue, negative = red.
// items: [{label, value, sub, lowData, tip}]
export function barChart(el, items, { format = (v) => pct(v), height = 200, labelEvery = 1 } = {}) {
  if (!items.length) { el.innerHTML = '<p class="muted small">No data yet.</p>'; return; }
  const W = Math.max(280, el.clientWidth), H = height;
  const m = { t: 22, r: 8, b: items.some((d) => d.sub) ? 38 : 24, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const vals = items.map((d) => d.value ?? 0);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const pad = (hi - lo || 0.01) * 0.12;
  const y0 = lo < 0 ? lo - pad : 0, y1 = hi + pad;
  const y = (v) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const band = iw / items.length, bw = Math.max(3, Math.min(56, band * 0.62));
  const pos = css("--series-1"), neg = css("--series-neg");
  const yt = ticks(y0, y1, 4);

  let svg = `<svg ${NS} viewBox="0 0 ${W} ${H}" height="${H}" role="img">`;
  svg += `<g class="grid">${yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>`).join("")}</g>`;
  svg += yt.map((v) => `<text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${esc(format(v))}</text>`).join("");
  svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--text-2)" stroke-width="1"/>`;
  items.forEach((d, i) => {
    const cx = m.l + band * i + band / 2;
    if (d.value != null) {
      const color = d.value >= 0 ? pos : neg;
      svg += `<path d="${bar(cx - bw / 2, y(0), y(d.value), bw)}" fill="${color}" opacity="${d.lowData ? 0.4 : 1}"/>`;
      if (items.length <= 8) {
        const ty = d.value >= 0 ? y(d.value) - 6 : y(d.value) + 14;
        svg += `<text x="${cx}" y="${ty}" text-anchor="middle" style="fill:var(--text)">${esc(format(d.value))}</text>`;
      }
    }
    if (i % labelEvery === 0) svg += `<text x="${cx}" y="${H - m.b + 15}" text-anchor="middle" style="fill:var(--text-2)">${esc(d.label)}</text>`;
    if (d.sub) svg += `<text x="${cx}" y="${H - m.b + 29}" text-anchor="middle">${esc(d.sub)}</text>`;
    svg += `<rect class="hit" data-i="${i}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${ih}" fill="transparent"/>`;
  });
  svg += "</svg>";
  el.innerHTML = svg;

  const tip = tooltip(el), svgEl = el.querySelector("svg");
  el.querySelectorAll(".hit").forEach((r) => {
    r.addEventListener("pointerenter", () => {
      const d = items[+r.dataset.i], box = svgEl.getBoundingClientRect(), s = box.width / W;
      const cx = m.l + band * +r.dataset.i + band / 2;
      tip.show(d.tip || `<strong>${esc(d.label)}</strong><br>${esc(format(d.value))}`, cx * s, (d.value >= 0 ? y(d.value ?? 0) : y(0)) * s);
    });
    r.addEventListener("pointerleave", () => tip.hide());
  });
}

// ---------------------------------------------------------------------------
// Horizontal bars around zero (one row per item). items: [{label, value, note, lowData, tip}]
export function hbarChart(el, items, { format = (v) => pct(v) } = {}) {
  if (!items.length) { el.innerHTML = '<p class="muted small">No data yet.</p>'; return; }
  const W = Math.max(280, el.clientWidth), rowH = 34;
  const m = { t: 6, r: 64, b: 6, l: Math.min(150, W * 0.36) };
  const H = m.t + m.b + rowH * items.length, iw = W - m.l - m.r;
  const vals = items.map((d) => d.value ?? 0);
  const ext = Math.max(0.005, ...vals.map(Math.abs)) * 1.1;
  const x = (v) => m.l + ((v + ext) / (2 * ext)) * iw;
  const pos = css("--series-1"), neg = css("--series-neg");
  let svg = `<svg ${NS} viewBox="0 0 ${W} ${H}" height="${H}" role="img">`;
  svg += `<line x1="${x(0)}" x2="${x(0)}" y1="${m.t}" y2="${H - m.b}" stroke="var(--text-2)"/>`;
  items.forEach((d, i) => {
    const yy = m.t + i * rowH, bh = 14, by = yy + (rowH - bh) / 2;
    svg += `<text x="${m.l - 8}" y="${by + 11}" text-anchor="end" style="fill:var(--text)">${esc(d.label)}</text>`;
    if (d.value != null) {
      svg += `<path d="${hbar(x(0), x(d.value), by, bh)}" fill="${d.value >= 0 ? pos : neg}" opacity="${d.lowData ? 0.4 : 1}"/>`;
      // positive: number after the bar end; negative: number just right of the zero line,
      // so it never runs into the row label on the left
      const tx = d.value >= 0 ? x(d.value) + 6 : x(0) + 6;
      svg += `<text x="${tx}" y="${by + 11}" text-anchor="start" style="fill:var(--text-2)">${esc(format(d.value))}${d.lowData ? " *" : ""}</text>`;
    } else {
      svg += `<text x="${x(0) + 6}" y="${by + 11}">no data</text>`;
    }
    svg += `<rect class="hit" data-i="${i}" x="0" y="${yy}" width="${W}" height="${rowH}" fill="transparent"/>`;
  });
  svg += "</svg>";
  el.innerHTML = svg;
  const tip = tooltip(el), svgEl = el.querySelector("svg");
  el.querySelectorAll(".hit").forEach((r) => {
    r.addEventListener("pointerenter", () => {
      const i = +r.dataset.i, d = items[i], s = svgEl.getBoundingClientRect().width / W;
      tip.show(d.tip || `<strong>${esc(d.label)}</strong><br>${esc(format(d.value))}`, x(d.value ?? 0) * s, (m.t + i * rowH + 6) * s);
    });
    r.addEventListener("pointerleave", () => tip.hide());
  });
}

// ---------------------------------------------------------------------------
// One 100% bar split into outcome segments. segs: [{label, value(0-1), color}]
export function splitBar(el, segs) {
  const total = segs.reduce((a, s) => a + (s.value || 0), 0) || 1;
  let left = 0;
  const parts = segs.filter((s) => s.value > 0).map((s) => {
    const w = (s.value / total) * 100;
    const part = `<div title="${esc(s.label)} ${Math.round(s.value * 100)}%" style="position:absolute;left:${left}%;width:calc(${w}% - 2px);top:0;bottom:0;background:${s.color};border-radius:4px"></div>`;
    left += w;
    return part;
  }).join("");
  el.innerHTML = `<div style="position:relative;height:16px;margin:4px 0 8px">${parts}</div>`
    + `<div class="legend">${segs.map((s) => `<span><i style="background:${s.color};height:10px;width:10px"></i>${esc(s.label)} ${Math.round((s.value || 0) * 100)}%</span>`).join("")}</div>`;
}
