// Hand-drawn SVG artwork: night scene banner, rarity gems, crest, emblems,
// wax seal, and the Reckoning boss. Colors use CSS tokens where it matters.

// Score -> rarity tier. Picks need 60+, so most quests are Rare or better.
export const TIERS = [
  { name: "Legendary", min: 80, gem: ["#fff1b8", "#e2b13c", "#8a5a08"] },
  { name: "Epic", min: 70, gem: ["#ecd2ff", "#a35ee0", "#4b1c78"] },
  { name: "Rare", min: 60, gem: ["#d4e6ff", "#4f8fe6", "#173f80"] },
  { name: "Common", min: 0, gem: ["#eeeae0", "#9a948a", "#4a463f"] },
];
export const tierOf = (score) => TIERS.find((t) => score >= t.min);

// A deterministic "random" so the stars don't jump around between renders.
function rand(seed) { let s = seed; return () => (s = (s * 16807) % 2147483647) / 2147483647; }

export function banner() {
  const r = rand(7);
  const stars = Array.from({ length: 70 }, () =>
    `<circle cx="${(r() * 1200).toFixed(0)}" cy="${(r() * 120).toFixed(0)}" r="${(r() * 1.3 + 0.3).toFixed(1)}" opacity="${(r() * 0.6 + 0.3).toFixed(2)}"/>`).join("");
  return `<svg class="banner-art" viewBox="0 0 1200 180" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0b0816"/><stop offset="1" stop-color="#2a1d45"/></linearGradient>
      <radialGradient id="moonglow"><stop offset="0" stop-color="#f6e7b0" stop-opacity=".55"/><stop offset="1" stop-color="#f6e7b0" stop-opacity="0"/></radialGradient>
      <linearGradient id="fog" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a1d45" stop-opacity="0"/><stop offset="1" stop-color="#120e1c"/></linearGradient>
    </defs>
    <rect width="1200" height="180" fill="url(#sky)"/>
    <g class="stars" fill="#fff">${stars}</g>
    <circle cx="960" cy="52" r="70" fill="url(#moonglow)"/>
    <circle cx="960" cy="52" r="22" fill="#f6e7b0"/><circle cx="968" cy="47" r="20" fill="#2a1d45" opacity=".18"/>
    <path d="M0 150 L80 112 L150 130 L240 86 L320 124 L410 96 L500 132 L590 92 L700 128 L790 98 L880 126 L980 90 L1080 122 L1200 100 V180 H0Z" fill="#231837"/>
    <path d="M0 165 L120 132 L230 150 L330 120 L470 158 L600 128 L720 150 L860 124 L1000 156 L1120 134 L1200 146 V180 H0Z" fill="#1a1229"/>
    <g fill="#120c1e">
      <path d="M210 160 V116 h10 v-8 h8 v8 h8 v-8 h8 v8 h10 V160Z"/>
      <path d="M232 108 V84 l8 -14 l8 14 V108Z"/>
      <path d="M262 160 V128 h40 V160Z"/><path d="M292 128 V100 l7 -12 l7 12 V128Z"/>
      <path d="M182 160 V132 h28 V160Z"/><path d="M186 132 V112 l6 -10 l6 10 V132Z"/>
    </g>
    <g fill="#f3b74f" class="windows"><rect x="238" y="92" width="4" height="7" rx="2"/><rect x="296" y="108" width="3.5" height="6" rx="1.7"/><rect x="226" y="130" width="4" height="6" rx="2"/></g>
    <rect y="120" width="1200" height="60" fill="url(#fog)"/>
  </svg>`;
}

export function gem(score, size = 64) {
  const t = tierOf(score), [hi, mid, lo] = t.gem, id = `g${Math.random().toString(36).slice(2, 8)}`;
  return `<svg class="gem gem-${t.name.toLowerCase()}" viewBox="0 0 64 64" width="${size}" height="${size}" role="img" aria-label="${t.name}, score ${score}">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${hi}"/><stop offset=".5" stop-color="${mid}"/><stop offset="1" stop-color="${lo}"/></linearGradient></defs>
    <polygon points="32,3 61,32 32,61 3,32" fill="url(#${id})" stroke="${lo}" stroke-width="2"/>
    <polygon points="32,3 46,32 32,61 18,32" fill="${hi}" opacity=".18"/>
    <polygon points="32,3 61,32 46,32" fill="#fff" opacity=".22"/>
    <polygon points="3,32 18,32 32,61" fill="#000" opacity=".18"/>
    <text x="32" y="38" text-anchor="middle" class="gem-num">${score}</text>
  </svg>`;
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"];
export const roman = (n) => ROMAN[n] || String(n);

export function crest(level, size = 44) {
  return `<svg class="crest" viewBox="0 0 48 56" width="${size}" height="${size * 56 / 48}" aria-hidden="true">
    <defs><linearGradient id="crestg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d77a"/><stop offset="1" stop-color="#a8781e"/></linearGradient></defs>
    <path d="M24 2 L45 9 V27 C45 41 35 50 24 54 C13 50 3 41 3 27 V9Z" fill="url(#crestg)" stroke="#3b2c12" stroke-width="2"/>
    <path d="M24 7 L40 12.5 V27 C40 38 32.5 45.5 24 49 C15.5 45.5 8 38 8 27 V12.5Z" fill="#2a1d45"/>
    <text x="24" y="34" text-anchor="middle" class="crest-num">${roman(level)}</text>
  </svg>`;
}

// Badge emblems (one per quest). Simple heraldic silhouettes.
const EMBLEMS = {
  boot: "M18 8h12v22l10 6c3 2 2 8-2 8H14c-2 0-3-2-3-4V30l7-4z",
  flame: "M26 4s3 8-3 15c-4 5-6 8-6 13a9 9 0 0 0 18 0c0-3-1-5-1-5s7 4 7 13c0 8-7 14-15 14S10 48 10 38c0-14 14-19 16-34z",
  crown: "M6 38 10 14l10 12 6-16 6 16 10-12 4 24zM6 42h40v6H6z",
  scroll: "M12 8h24a6 6 0 0 1 6 6v26a6 6 0 0 1-6 6H16a6 6 0 0 1-6-6V14h-2a4 4 0 0 1 4-6zm6 10v3h18v-3zm0 8v3h18v-3zm0 8v3h12v-3z",
  oath: "M26 4 6 12v12c0 12 8 22 20 26 12-4 20-14 20-26V12zm-3 30-8-8 3-3 5 5 11-11 3 3z",
  hourglass: "M12 4h28v4h-3c0 9-6 13-9 16 3 3 9 7 9 16h3v4H12v-4h3c0-9 6-13 9-16-3-3-9-7-9-16h-3zm8 4c0 6 4 10 6 12 2-2 6-6 6-12z",
  eye: "M26 12C14 12 6 26 6 26s8 14 20 14 20-14 20-14-8-14-20-14zm0 22a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm0-5a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  key: "M18 6a12 12 0 0 0-3 23.6V46h8v-4h5v-5h-5v-7.4A12 12 0 0 0 18 6zm0 6a5 5 0 1 1 0 10 5 5 0 0 1 0-10z",
};
export function emblem(name, size = 34) {
  return `<svg viewBox="0 0 52 52" width="${size}" height="${size}" aria-hidden="true"><path d="${EMBLEMS[name] || EMBLEMS.scroll}"/></svg>`;
}

export function seal(text = "SQ") {
  return `<svg class="seal-svg" viewBox="0 0 80 80" aria-hidden="true">
    <path d="M40 4c6 0 8 5 13 6s10-1 13 4 0 9 2 13 7 7 6 13-6 7-7 12 2 10-3 14-9 1-13 3-6 7-12 7-8-5-13-6-10 1-13-4 0-9-2-13-7-7-6-13 6-7 7-12-2-10 3-14 9-1 13-3 6-7 12-7z" fill="#8f1d1d"/>
    <circle cx="40" cy="40" r="24" fill="none" stroke="#5e1010" stroke-width="3"/>
    <circle cx="40" cy="40" r="24" fill="none" stroke="#c0423f" stroke-width="1" opacity=".6"/>
    <text x="40" y="47" text-anchor="middle" class="seal-text">${text}</text>
  </svg>`;
}

export function boss(defeated = false) {
  return `<svg class="boss-svg ${defeated ? "defeated" : ""}" viewBox="0 0 200 200" aria-hidden="true">
    <defs><radialGradient id="aura"><stop offset="0" stop-color="#7c3aed" stop-opacity=".55"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient></defs>
    <circle cx="100" cy="100" r="95" fill="url(#aura)" class="aura"/>
    <path class="body" d="M100 18c-30 0-48 26-48 58 0 22 6 36 2 56-3 14-18 30-18 44 12-6 20-2 28 4 6-8 14-10 22-4 8-8 20-8 28 0 8-6 16-4 22 4 8-6 16-10 28-4 0-14-15-30-18-44-4-20 2-34 2-56 0-32-18-58-48-58z" fill="#1b1030"/>
    <path d="M70 70c8-14 52-14 60 0-6 18-54 18-60 0z" fill="#0a0612"/>
    <g class="eyes"><ellipse cx="86" cy="74" rx="6" ry="4" fill="#ff5a5a"/><ellipse cx="114" cy="74" rx="6" ry="4" fill="#ff5a5a"/></g>
    <path d="M58 120c-14 4-26 14-30 26 10-4 18-2 26 2M142 120c14 4 26 14 30 26-10-4-18-2-26 2" stroke="#1b1030" stroke-width="10" stroke-linecap="round" fill="none"/>
  </svg>`;
}

export function flourish() {
  return `<svg class="flourish" viewBox="0 0 240 16" aria-hidden="true"><path d="M0 8h96M144 8h96" stroke="currentColor" stroke-width="1"/>
    <path d="M120 2l6 6-6 6-6-6z M104 8a4 4 0 1 0 8 0 4 4 0 1 0-8 0 M128 8a4 4 0 1 0 8 0 4 4 0 1 0-8 0" fill="currentColor"/></svg>`;
}

export function torch(size = 18) {
  return `<svg class="torch" viewBox="0 0 24 32" width="${size}" height="${size * 4 / 3}" aria-hidden="true">
    <path class="flame-outer" d="M12 1c2 4 7 6 7 12a7 7 0 0 1-14 0c0-3 2-5 3-7 0 3 2 4 3 4-1-3 0-6 1-9z" fill="#ff9f43"/>
    <path class="flame-inner" d="M12 8c1 2 4 4 4 7a4 4 0 0 1-8 0c0-2 1-3 2-4 0 2 1 2 2 2-.5-2 0-3 0-5z" fill="#ffe08a"/>
    <path d="M8 20h8l-2 11h-4z" fill="#6d4a22"/></svg>`;
}

export function noticeBoard() {
  return `<svg viewBox="0 0 220 150" class="board-art" aria-hidden="true">
    <rect x="20" y="14" width="180" height="112" rx="6" fill="#4a3220" stroke="#2b1c10" stroke-width="4"/>
    <rect x="30" y="24" width="160" height="92" rx="3" fill="#5e4129"/>
    <path d="M40 126v20M180 126v20" stroke="#2b1c10" stroke-width="6"/>
    <g transform="rotate(-4 110 70)"><rect x="82" y="40" width="56" height="62" fill="#e8d7ad"/><path d="M90 54h40M90 64h40M90 74h28" stroke="#9c8558" stroke-width="3"/></g>
    <circle cx="110" cy="40" r="4" fill="#b8913f"/>
    <g class="candle"><rect x="176" y="96" width="8" height="18" fill="#efe2bf"/><path d="M180 84c3 4 4 6 4 8a4 4 0 0 1-8 0c0-2 1-4 4-8z" fill="#ffb347"/></g>
  </svg>`;
}
