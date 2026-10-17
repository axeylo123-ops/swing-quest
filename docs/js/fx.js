// Effects: drifting embers, XP sparks, wax-seal stamp, level-up fanfare,
// card tilt, shake, and counting numbers. All honor "reduce motion".
import { crest, seal } from "./art.js";

export const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- background embers (one fixed canvas behind everything) ----
export function embers() {
  if (calm()) return;
  const c = document.createElement("canvas");
  c.className = "embers";
  document.body.prepend(c);
  const ctx = c.getContext("2d");
  let w, h, dpr;
  const resize = () => {
    dpr = Math.min(2, devicePixelRatio || 1);
    w = c.width = innerWidth * dpr; h = c.height = innerHeight * dpr;
  };
  resize(); addEventListener("resize", resize);
  const N = innerWidth < 600 ? 18 : 36;
  const motes = Array.from({ length: N }, () => spawn(true));
  function spawn(anywhere) {
    return { x: Math.random() * w, y: anywhere ? Math.random() * h : h + 10, r: (Math.random() * 1.6 + 0.6) * dpr,
      vy: -(Math.random() * 0.25 + 0.08) * dpr, vx: (Math.random() - 0.5) * 0.15 * dpr, a: Math.random() * 0.5 + 0.2, t: Math.random() * 6 };
  }
  let last = 0;
  (function tick(ts) {
    if (!document.hidden && ts - last > 33) {   // ~30 fps is plenty
      last = ts;
      ctx.clearRect(0, 0, w, h);
      for (const m of motes) {
        m.t += 0.03; m.x += m.vx + Math.sin(m.t) * 0.15 * dpr; m.y += m.vy;
        if (m.y < -10) Object.assign(m, spawn(false));
        ctx.globalAlpha = m.a * (0.6 + 0.4 * Math.sin(m.t * 2));
        ctx.fillStyle = "#f3b74f";
        ctx.beginPath(); ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2); ctx.fill();
      }
    }
    requestAnimationFrame(tick);
  })(0);
}

// ---- gold sparks flying from an element to the XP crest ----
export function sparks(fromEl, count = 12) {
  const to = document.querySelector("#player .crest");
  if (!fromEl || !to || calm()) return;
  const a = fromEl.getBoundingClientRect(), b = to.getBoundingClientRect();
  const sx = a.left + a.width / 2, sy = a.top + a.height / 2, tx = b.left + b.width / 2, ty = b.top + b.height / 2;
  for (let i = 0; i < count; i++) {
    const s = document.createElement("i");
    s.className = "spark";
    document.body.appendChild(s);
    const mx = sx + (Math.random() - 0.5) * 160, my = sy - 60 - Math.random() * 80;
    const dur = 650 + Math.random() * 350, delay = i * 25;
    s.animate([
      { transform: `translate(${sx}px, ${sy}px) scale(1)`, opacity: 1 },
      { transform: `translate(${mx}px, ${my}px) scale(1.2)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${tx}px, ${ty}px) scale(.4)`, opacity: 0.2 },
    ], { duration: dur, delay, easing: "cubic-bezier(.4,0,.2,1)" }).onfinish = () => s.remove();
  }
  setTimeout(() => to.animate([{ transform: "scale(1)" }, { transform: "scale(1.25)" }, { transform: "scale(1)" }],
    { duration: 380, easing: "ease-out" }), 800);
}

// ---- wax seal stamped onto a quest scroll ----
export function stamp(card) {
  if (!card || card.querySelector(".stamped")) return;
  const s = document.createElement("div");
  s.className = "stamped";
  s.innerHTML = seal("SQ");
  card.appendChild(s);
  if (!calm()) s.animate([
    { transform: "scale(2.4) rotate(-30deg)", opacity: 0 },
    { transform: "scale(.9) rotate(-12deg)", opacity: 1, offset: 0.7 },
    { transform: "scale(1) rotate(-12deg)", opacity: 1 },
  ], { duration: 420, easing: "cubic-bezier(.2,.8,.2,1.2)" });
}

// ---- level-up fanfare ----
export function levelUp(level, title) {
  const o = document.createElement("div");
  o.className = "levelup";
  o.setAttribute("role", "dialog");
  o.setAttribute("aria-label", `Level up: level ${level}, ${title}`);
  o.innerHTML = `<div class="rays"></div><div class="levelup-card">${crest(level, 110)}
    <div class="lu-kicker">Level up</div><div class="lu-title">${title}</div><div class="lu-sub">You reached level ${level}. Tap to continue.</div></div>`;
  document.body.appendChild(o);
  const close = () => { o.classList.add("closing"); setTimeout(() => o.remove(), 300); };
  o.addEventListener("click", close);
  setTimeout(close, 5000);
}

// ---- subtle 3D tilt on hover (desktop pointers only) ----
export function tilt(el, max = 4) {
  if (calm() || !matchMedia("(hover: hover)").matches) return;
  el.addEventListener("pointermove", (e) => {
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `perspective(900px) rotateY(${x * max}deg) rotateX(${-y * max}deg)`;
  });
  el.addEventListener("pointerleave", () => { el.style.transform = ""; });
}

export function shake(el) {
  if (calm() || !el) return;
  el.animate([{ transform: "translateX(0)" }, { transform: "translateX(-8px)" }, { transform: "translateX(8px)" },
    { transform: "translateX(-5px)" }, { transform: "translateX(0)" }], { duration: 320 });
}

// ---- numbers that count up to their value ----
export function countUp(el, to, format = (v) => String(Math.round(v)), ms = 700) {
  if (calm() || to == null || !Number.isFinite(to)) { el.textContent = to == null ? "–" : format(to); return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms), e = 1 - (1 - t) ** 3;
    el.textContent = format(to * e);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---- floating "+N" damage / xp number ----
export function floatText(el, text, cls = "") {
  if (!el) return;
  const r = el.getBoundingClientRect();
  const f = document.createElement("div");
  f.className = `float-text ${cls}`;
  f.textContent = text;
  f.style.left = `${r.left + r.width / 2}px`; f.style.top = `${r.top + 10}px`;
  document.body.appendChild(f);
  f.animate([{ transform: "translate(-50%, 0)", opacity: 1 }, { transform: "translate(-50%, -60px)", opacity: 0 }],
    { duration: calm() ? 1 : 900, easing: "ease-out" }).onfinish = () => f.remove();
}
