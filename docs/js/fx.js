// Effects: XP sparks, level-up flash, counting numbers, floating text, shake.
// All of them respect "reduce motion".

export const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Neon sparks flying from an element to the level badge in the top bar.
export function sparks(fromEl, count = 10) {
  const to = document.querySelector("#player .lvl");
  if (!fromEl || !to || calm()) return;
  const a = fromEl.getBoundingClientRect(), b = to.getBoundingClientRect();
  const sx = a.left + a.width / 2, sy = a.top + a.height / 2, tx = b.left + b.width / 2, ty = b.top + b.height / 2;
  for (let i = 0; i < count; i++) {
    const s = document.createElement("i");
    s.className = "spark";
    document.body.appendChild(s);
    const mx = sx + (Math.random() - 0.5) * 140, my = sy - 40 - Math.random() * 70;
    s.animate([
      { transform: `translate(${sx}px, ${sy}px) rotate(45deg)`, opacity: 1 },
      { transform: `translate(${mx}px, ${my}px) rotate(45deg)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${tx}px, ${ty}px) rotate(45deg) scale(.3)`, opacity: 0.2 },
    ], { duration: 600 + Math.random() * 300, delay: i * 22, easing: "cubic-bezier(.4,0,.2,1)" }).onfinish = () => s.remove();
  }
  setTimeout(() => to.animate([{ boxShadow: "0 0 0 transparent" }, { boxShadow: "0 0 18px #44d62c" }, { boxShadow: "0 0 0 transparent" }], { duration: 500 }), 700);
}

export function levelUp(level, title) {
  const o = document.createElement("div");
  o.className = "levelup";
  o.setAttribute("role", "dialog");
  o.innerHTML = `<div class="levelup-card"><div class="lu-kicker">LEVEL UP</div><div class="lu-title">${title}</div>
    <div class="lu-sub">Level ${level} reached. Tap to continue.</div></div>`;
  document.body.appendChild(o);
  const close = () => { o.classList.add("closing"); setTimeout(() => o.remove(), 300); };
  o.addEventListener("click", close);
  setTimeout(close, 4000);
}

export function countUp(el, to, format = (v) => String(Math.round(v)), ms = 650) {
  if (!el) return;
  if (calm() || to == null || !Number.isFinite(to)) { el.textContent = to == null ? "–" : format(to); return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms), e = 1 - (1 - t) ** 3;
    el.textContent = format(to * e);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export function floatText(el, text) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  const f = document.createElement("div");
  f.className = "float-text";
  f.textContent = text;
  f.style.left = `${r.left + r.width / 2}px`; f.style.top = `${r.top}px`;
  document.body.appendChild(f);
  f.animate([{ transform: "translate(-50%, 0)", opacity: 1 }, { transform: "translate(-50%, -50px)", opacity: 0 }],
    { duration: calm() ? 1 : 850, easing: "ease-out" }).onfinish = () => f.remove();
}

export function shake(el) {
  if (calm() || !el) return;
  el.animate([{ transform: "translateX(0)" }, { transform: "translateX(-6px)" }, { transform: "translateX(6px)" }, { transform: "translateX(0)" }], { duration: 260 });
}
