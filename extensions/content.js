const MAX_CHARS = 350,
  MAX_TURNS = 10,
  COOLDOWN = 1800;
const TEST_MODE = false;

const SHOW_SCAN_OUTLINE = true;

/* ---------------- Overlay ---------------- */
function overlay() {
  let el = document.getElementById("qrizz-lite");
  if (!el) {
    el = document.createElement("div");
    el.id = "qrizz-lite";
    Object.assign(el.style, {
      position: "fixed",
      zIndex: 2147483647,
      background: "transparent",
      color: "#000",
      fontFamily: "system-ui",
      fontSize: "13px",
      pointerEvents: "auto",
      userSelect: "none",
      bottom: "16px",
      right: "16px",
      left: "auto",
      top: "auto",
      maxWidth: "42vw",
      minWidth: "320px",
    });

    // Launcher (collapsed state)
    const launcher = document.createElement("button");
    launcher.id = "qr-launch";
    launcher.textContent = "Activate Wingman";
    Object.assign(launcher.style, wingmanButtonStyle("#111", "#fff"));
    launcher.style.padding = "10px 14px";
    launcher.style.boxShadow = "0 6px 18px rgba(0,0,0,.15)";
    launcher.style.borderRadius = "999px";
    launcher.style.transition =
      "transform .15s ease, background .15s ease, color .15s ease";
    launcher.addEventListener(
      "mouseenter",
      () => (launcher.style.transform = "translateY(-1px) scale(1.03)")
    );
    launcher.addEventListener(
      "mouseleave",
      () => (launcher.style.transform = "translateY(0) scale(1)")
    );
    launcher.addEventListener(
      "mousedown",
      () => (launcher.style.transform = "translateY(0) scale(0.98)")
    );
    launcher.addEventListener(
      "mouseup",
      () => (launcher.style.transform = "translateY(-1px) scale(1.03)")
    );

    // Panel
    const panel = document.createElement("div");
    panel.id = "qr-panel";
    Object.assign(panel.style, wingmanPanelStyle());
    panel.style.display = "none";
    panel.innerHTML = `
      <div id="qr-panel-inner" style="position:relative; display:flex; flex-direction:column; gap:10px; width:100%; height:100%;">
        <div id="qr-heat-aura" style="position:absolute; inset:0; pointer-events:none;"></div>

        <div id="qr-head" style="display:flex;align-items:center;gap:8px;">
          <div style="font-weight:700; font-size:13px; letter-spacing:.2px;">Wingman</div>
          <span id="qr-heat-pill" style="margin-left:4px;padding:2px 8px;border-radius:999px;border:1px solid #ddd;font-size:11px;font-weight:600;color:#ef4444;display:flex;align-items:center;gap:4px;">🔥 H1</span>
          <span id="qr-stage-pill" style="padding:2px 8px;border-radius:999px;border:1px solid #ddd;font-size:11px;font-weight:600;color:#333;">📍 BANter</span>
          <span id="qr-status" style="margin-left:auto;padding:0;border:0;font-size:0;opacity:0;pointer-events:none;">ready</span>
        </div>

        <!-- Loading state -->
        <div id="qr-loading" style="display:none;flex:1;min-height:120px;align-items:center;justify-content:center;">
          <div id="qr-spinner" style="${spinnerStyle()}"></div>
        </div>

        <!-- Options grid -->
        <div id="qr-grid" style="display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px;"></div>

        <!-- Footer actions -->
        <div id="qr-footer" style="display:flex;align-items:center;gap:8px;margin-top:2px;">
          <button id="qr-commit" style="${footerBtnStyle(
            "#0ea5e9"
          )}">Commit</button>
          <button id="qr-reset"  style="${footerBtnStyle(
            "#a855f7"
          )}">Reset</button>
          <div style="margin-left:auto;display:flex;align-items:center;gap:8px;">
            <button id="qr-close" style="${closeBtnStyle()}">take it from here</button>
          </div>
        </div>
      </div>
    `;

    el.appendChild(launcher);
    el.appendChild(panel);
    el.insertAdjacentHTML(
      "beforeend",
      `<div id="qr-body" style="display:none;"></div>`
    ); // legacy anchor

    // Open/close wiring
    launcher.addEventListener("click", () => {
      if (launcher.__dragJustHappened) return; // drag guard
      launcher.style.display = "none"; // instant hide on open
      expandWingman();
    });
    panel
      .querySelector("#qr-close")
      .addEventListener("click", () => collapseWingmanWithHype());

    document.documentElement.appendChild(el);

    // Enable dragging in collapsed state
    enableLauncherDrag();
  }
  return el;
}
function bodyEl() {
  overlay(); // ensure created
  const panel = document.getElementById("qr-panel");
  return panel || document.getElementById("qr-body");
}

/* ---------- Wingman UI helpers  ---------- */
function wingmanPanelStyle() {

  return {
    position: "relative",
    width: "min(35.7vw, 442px)",
    minWidth: "320px",
    maxWidth: "442px",
    minHeight: "150px",
    padding: "12px",
    background: "linear-gradient(180deg, #ffffff 0%, #fafafa 100%)",
    color: "#111",
    border: "1px solid #e5e7eb",
    borderRadius: "14px",
    boxShadow:
      "0 10px 28px rgba(0,0,0,.15), inset 0 0 0 1px rgba(255,255,255,.6)",
    backdropFilter: "saturate(1.1) blur(0px)",
  };
}
function wingmanButtonStyle(bg = "#111", fg = "#fff") {
  return {
    background: bg,
    color: fg,
    border: "1px solid rgba(0,0,0,.1)",
    borderRadius: "10px",
    cursor: "pointer",
  };
}
function footerBtnStyle(color) {
  return `
    border:none;background:${color};color:#fff;
    padding:8px 12px;border-radius:10px;cursor:pointer;
    font-weight:600;letter-spacing:.2px;box-shadow:0 6px 16px rgba(0,0,0,.15);
    transition:transform .12s ease, filter .12s ease, opacity .12s ease;
  `;
}
function closeBtnStyle() {
  return `
    border:1px solid #e5e7eb;background:#111;color:#fff;
    padding:8px 12px;border-radius:999px;cursor:pointer;font-weight:700;
    box-shadow:0 6px 16px rgba(0,0,0,.18);transition:transform .12s ease, opacity .12s ease, background .12s ease;
  `;
}
function spinnerStyle() {
  return `
    width:34px;height:34px;border:3px solid rgba(17,17,17,.15);
    border-top-color:#111;border-radius:50%;animation:qrspin 0.8s linear infinite;
  `;
}
(function ensureSpinnerKeyframes() {
  if (document.getElementById("qrspin-style")) return;
  const st = document.createElement("style");
  st.id = "qrspin-style";
  st.textContent = `
    @keyframes qrspin { to { transform: rotate(360deg); } }
    .qr-chip:hover { transform: translateY(-1px) scale(1.02); filter: brightness(1.04); }
    .qr-chip:active { transform: translateY(0) scale(0.98); filter: brightness(0.98); }
  `;
  document.head.appendChild(st);
})();

// Launcher drag state (collapsed only)
let __wingmanOpen = false;
let __dragActive = false;
let __dragStart = { x: 0, y: 0 };
let __dragOffset = { x: 0, y: 0 };
let __dragMoved = false;

function enableLauncherDrag() {
  const root = overlay();
  const launcher = root.querySelector("#qr-launch");
  if (!launcher || launcher.__dragBound) return;

  // Reset “just dragged” flag before each interaction
  launcher.addEventListener(
    "mousedown",
    (e) => (launcher.__dragJustHappened = false)
  );

  const down = (e) => {
    if (__wingmanOpen) return; // only when collapsed
    __dragActive = true;
    __dragMoved = false;

    // Switch container to top/left positioning for smooth free drag
    const host = root;
    const rect = host.getBoundingClientRect();
    const startX = e.touches ? e.touches[0].clientX : e.clientX;
    const startY = e.touches ? e.touches[0].clientY : e.clientY;

    // Convert current bottom/right into explicit top/left
    const top = rect.top;
    const left = rect.left;
    host.style.top = `${Math.max(
      0,
      Math.min(window.innerHeight - rect.height, top)
    )}px`;
    host.style.left = `${Math.max(
      0,
      Math.min(window.innerWidth - rect.width, left)
    )}px`;
    host.style.right = "auto";
    host.style.bottom = "auto";

    __dragStart = { x: startX, y: startY };
    __dragOffset = { x: left, y: top };

    window.addEventListener("mousemove", move, { passive: false });
    window.addEventListener("mouseup", up, { passive: false });
    window.addEventListener("touchmove", move, { passive: false });
    window.addEventListener("touchend", up, { passive: false });
  };

  const move = (e) => {
    if (!__dragActive || __wingmanOpen) return;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;

    const dx = clientX - __dragStart.x;
    const dy = clientY - __dragStart.y;
    if (Math.abs(dx) + Math.abs(dy) > 5) __dragMoved = true;

    const host = root;
    const rect = host.getBoundingClientRect();
    let nx = __dragOffset.x + dx;
    let ny = __dragOffset.y + dy;

    // Constrain to viewport
    nx = Math.max(0, Math.min(window.innerWidth - rect.width, nx));
    ny = Math.max(0, Math.min(window.innerHeight - rect.height, ny));

    host.style.left = `${nx}px`;
    host.style.top = `${ny}px`;

    // prevent accidental text selection while dragging
    e.preventDefault();
  };

  const up = () => {
    if (!__dragActive) return;
    __dragActive = false;

    // Mark that a drag happened so the immediate click doesn’t open the panel unintentionally
    if (__dragMoved) {
      launcher.__dragJustHappened = true;
      // Clear flag after a short delay so future clicks work
      setTimeout(() => (launcher.__dragJustHappened = false), 150);
    }

    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", up);
    window.removeEventListener("touchmove", move);
    window.removeEventListener("touchend", up);
  };

  launcher.addEventListener("mousedown", down, { passive: false });
  launcher.addEventListener("touchstart", down, { passive: false });

  launcher.__dragBound = true;
}

function disableLauncherDrag() {
  const root = overlay();
  const launcher = root.querySelector("#qr-launch");
  if (!launcher || !launcher.__dragBound) return;

  launcher.__dragJustHappened = false;
  launcher.__dragBound = false;

  launcher.replaceWith(launcher.cloneNode(true)); // remove all handlers cleanly
  const fresh = overlay().querySelector("#qr-launch");
  // Rewire only the click (drag is disabled while expanded)
  fresh.addEventListener("click", () => {
    if (fresh.__dragJustHappened) return;
    fresh.style.display = "none"; // ensure instant hide
    expandWingman();
  });
}

/* Open/close */
function expandWingman() {
  const root = overlay();
  const launcher = root.querySelector("#qr-launch");
  const panel = root.querySelector("#qr-panel");
  if (!panel || !launcher) return;

  // Disable dragging while active
  disableLauncherDrag();

  launcher.style.display = "none"; // ensure hidden
  panel.style.display = "block";
  __wingmanOpen = true;
  panel.animate(
    [
      { transform: "scale(0.96)", opacity: 0 },
      { transform: "scale(1)", opacity: 1 },
    ],
    { duration: 120, easing: "ease-out" }
  );
}

// Toast anchored over the launcher button
function showAnchoredToastOverLauncher(msg, launcherRect) {
  let t = document.getElementById("qr-toast-anchored");
  if (!t) {
    t = document.createElement("div");
    t.id = "qr-toast-anchored";
    Object.assign(t.style, {
      position: "fixed",
      padding: "8px 10px",
      border: "1px solid #111",
      borderRadius: "10px",
      background: "#111",
      color: "#fff",
      fontSize: "12px",
      boxShadow: "0 8px 18px rgba(0,0,0,.3)",
      opacity: "0",
      zIndex: 2147483647,
      fontWeight: 700,
      pointerEvents: "none",
      transform: "translate(-50%, 0)",
    });
    document.documentElement.appendChild(t);
  }
  t.textContent = msg;

  const gap = 8; // vertical spacing below the button
  const left = launcherRect.left + launcherRect.width / 2;
  const top = launcherRect.bottom + gap;
  t.style.left = `${left}px`;
  t.style.top = `${top}px`;

  t.animate(
    [
      { opacity: 0, transform: "translate(-50%, 12px)" },
      { opacity: 1, transform: "translate(-50%, 0)" },
    ],
    { duration: 140, easing: "ease-out", fill: "forwards" }
  );
  clearTimeout(t._hide);
  t._hide = setTimeout(() => {
    t.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: 180,
      easing: "ease-in",
      fill: "forwards",
    });
  }, 1200);
}

function collapseWingmanWithHype() {
  const luck = goodLuckByHeat(window.__qr_spice || 1);

  const root = overlay();
  const panel = root.querySelector("#qr-panel");
  const launcher = root.querySelector("#qr-launch");
  if (!panel || !launcher) return;

  panel.animate(
    [
      { transform: "scale(1)", opacity: 1 },
      { transform: "scale(0.96)", opacity: 0 },
    ],
    { duration: 140, easing: "ease-in" }
  ).onfinish = () => {
    panel.style.display = "none";
    launcher.textContent = "Activate Wingman";
    launcher.style.display = "inline-block"; // reshow
    __wingmanOpen = false;

    // Now that the launcher is visible, anchor the toast to it
    const rect = launcher.getBoundingClientRect();
    showAnchoredToastOverLauncher(luck, rect);

    // Re-enable dragging now that we’re collapsed again
    enableLauncherDrag();
  };
}

function goodLuckByHeat(h) {
  const idx = Math.max(0, Math.min(4, Number(h) || 1));
  const map = {
    0: "You got this. Smooth & easy.",
    1: "Clean delivery. Keep it playful.",
    2: "🔥 Momentum’s yours. Go seal it.",
    3: "😈🔥 All you, ma boy. It’s in the bag.",
    4: "😈🔥💦 Lock it in, ur already in 🔥",
  };
  return map[idx] || map[1];
}
function hypeToast(text) {
  const root = overlay();
  let t = root.querySelector("#qr-hype");
  if (!t) {
    t = document.createElement("div");
    t.id = "qr-hype";
    Object.assign(t.style, {
      position: "fixed",
      bottom: "16px",
      right: "16px",
      maxWidth: "54vw",
      background: "#111",
      color: "#fff",
      padding: "10px 12px",
      borderRadius: "12px",
      border: "1px solid rgba(255,255,255,.08)",
      boxShadow: "0 8px 22px rgba(0,0,0,.35)",
      opacity: "0",
      transform: "translateY(8px)",
      pointerEvents: "none",
      zIndex: 2147483647,
      fontWeight: 700,
    });
    document.documentElement.appendChild(t);
  }
  t.textContent = text;
  t.animate(
    [
      { opacity: 0, transform: "translateY(8px)" },
      { opacity: 1, transform: "translateY(0)" },
    ],
    { duration: 140, easing: "ease-out", fill: "forwards" }
  );
  clearTimeout(t._hide);
  t._hide = setTimeout(() => {
    t.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: 180,
      easing: "ease-in",
      fill: "forwards",
    });
  }, 1200);
}


function spawnHeatEmojis(heat) {
  if (!__wingmanOpen) return;
  const root = overlay().querySelector("#qr-heat-aura");
  if (!root) return;
  const ems = heat >= 3 ? ["😈", "🔥"] : heat >= 2 ? ["🔥"] : [];
  if (!ems.length) return;
  const count = heat >= 3 ? 5 : 3;
  for (let i = 0; i < count; i++) {
    const e = document.createElement("div");
    e.textContent = ems[Math.floor(Math.random() * ems.length)];
    Object.assign(e.style, {
      position: "absolute",
      left: `${10 + Math.random() * 80}%`,
      bottom: "6%",
      fontSize: `${14 + Math.random() * 10}px`,
      opacity: "0",
      pointerEvents: "none",
      filter:
        heat >= 3
          ? "drop-shadow(0 2px 6px rgba(239,68,68,.6))"
          : "drop-shadow(0 2px 6px rgba(245,158,11,.45))",
    });
    root.appendChild(e);
    const dy = 40 + Math.random() * 50;
    e.animate(
      [
        { transform: "translate(-50%, 6px) scale(0.9)", opacity: 0 },
        {
          transform: `translate(-50%, -${dy}px) scale(1.05)`,
          opacity: 1,
          offset: 0.4,
        },
        { transform: `translate(-50%, -${dy + 10}px) scale(1.05)`, opacity: 0 },
      ],
      { duration: 900 + Math.random() * 300, easing: "ease-out" }
    ).onfinish = () => e.remove();
  }
}

/* ---------------- Small helpers ---------------- */

function showToast(msg) {
  const root = overlay();
  let t = root.querySelector("#qr-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "qr-toast";
    Object.assign(t.style, {
      position: "fixed",
      right: "16px",
      bottom: "16px",
      padding: "8px 10px",
      border: "1px solid #111",
      borderRadius: "10px",
      background: "#111",
      color: "#fff",
      fontSize: "12px",
      boxShadow: "0 8px 18px rgba(0,0,0,.3)",
      opacity: "0",
      transition: "opacity .15s ease",
      pointerEvents: "none",
      zIndex: 2147483647,
      fontWeight: 700,
    });
    document.documentElement.appendChild(t);
  }
  t.textContent = msg;
  requestAnimationFrame(() => (t.style.opacity = "1"));
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.opacity = "0"), 1000);
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  showToast(" Copied!");
}

// NEW ---- Commit snapshot state ----
window.__qr_pending = null;

function makeSnapshot(latestText, stage, heat, options) {
  const now = Date.now();
  return {
    text: latestText || "",
    stage: stage || "banter",
    heat: typeof heat === "number" ? heat : 1,
    options: (options || []).map((o) => ({
      resp: String(o),
      stage: stage || "banter",
      heat: typeof heat === "number" ? heat : 1,
      rating: null,
      reason: "",
      ts: now,
    })),
  };
}

function commitSnapshot(p) {
  if (!p || !p.text || !Array.isArray(p.options) || !p.options.length) {
    showToast("Nothing to commit");
    return;
  }
  return askBackend("qr_commit", {
    text: p.text,
    stage: p.stage,
    heat: p.heat,
    options: p.options.map((it) => ({
      text: it.resp,
      rating: it.rating,
      reason: it.reason,
    })),
  }).then((resp) => showToast(resp?.ok ? " Committed" : "Commit failed"));
}

/* ---------------- SITE ADAPTERS ---------------- */
const ADAPTERS = {
  "instagram.com": {
    threadId: () => location.pathname,
    containerSelector: 'main, [role="main"]',
  },
  "web.whatsapp.com": {
    threadId: () => location.href.split("/").slice(0, 5).join("/"),
    containerSelector: '#main div[role="region"]',
  },
  "messenger.com": {
    threadId: () => location.pathname,
    containerSelector: '[role="main"] [role="log"], [role="main"]',
  },
};
function pickAdapter() {
  const h = location.hostname;
  for (const k of Object.keys(ADAPTERS)) if (h.endsWith(k)) return ADAPTERS[k];
  return {
    threadId: () => location.pathname,
    containerSelector: '[role="main"], [role="log"], main, body',
  };
}
const AD = pickAdapter();

/* ---------------- Context store (per thread) ---------------- */
const clamp = (s) => (s || "").trim().replace(/\s+/g, " ").slice(0, MAX_CHARS);
function sanitizeCtx(x) {
  if (!Array.isArray(x)) return [];
  return x
    .filter(
      (m) =>
        m &&
        (m.role === "them" || m.role === "you") &&
        typeof m.text === "string"
    )
    .map((m) => ({
      role: m.role,
      text: clamp(m.text),
      ts: Number(m.ts) || Date.now(),
    }))
    .slice(-MAX_TURNS);
}
function getThreadId() {
  try {
    return AD.threadId() || location.href;
  } catch {
    return location.href;
  }
}

let __thread = null;
function ctxKey() {
  return "qr_ctx:" + getThreadId();
}
function loadCtx() {
  try {
    return sanitizeCtx(JSON.parse(localStorage.getItem(ctxKey()) || "[]"));
  } catch {
    return [];
  }
}
function saveCtx(arr) {
  try {
    localStorage.setItem(ctxKey(), JSON.stringify(sanitizeCtx(arr)));
  } catch {}
}

let ctx = loadCtx();
let lastSeenText = "",
  lastSeenRole = "";
function maybeThreadRotate() {
  const t = getThreadId();
  if (__thread !== t) {
    __thread = t;
    ctx = loadCtx();
    lastSeenText = "";
    lastSeenRole = "";
  }
}
setInterval(maybeThreadRotate, 500);

/* ---------------- Fresh-convo detector ---------------- */
const GREETING_RX =
  /^(he(y+|llo)|hi+|yo|sup|hru|wyd|gm|gn|hey there|hi there)[\s!?]*$/i;
function softResetIfNewConversation(latest, history) {
  const now = Date.now();
  const lastYou = [...history].reverse().find((m) => m.role === "you");
  const gapOk = lastYou ? now - (lastYou.ts || now) > 20 * 60 * 1000 : true;
  if (latest.role === "them" && GREETING_RX.test(latest.text) && gapOk) {
    ctx = [{ role: "them", text: latest.text, ts: now }];
    saveCtx(ctx);
    return true;
  }
  return false;
}

/* ---------------- Scraping ---------------- */
function toBubble(el) {
  return (
    el?.closest?.(
      '[role="listitem"], [role="row"], article, li, [data-testid*="message"]'
    ) || el
  );
}
function getComposerRect() {
  const sel = [
    'main [contenteditable="true"]',
    '[role="textbox"][contenteditable="true"]',
    '[contenteditable="true"][aria-label]',
    "textarea",
  ].join(", ");
  const cand = document.querySelector(sel);
  if (!cand) return null;
  const r = cand.getBoundingClientRect();
  if (r.width < 120 || r.height < 20) return null;
  return r;
}

// Add this helper above getChatRoot()
function findScrollParent(el) {
  while (el && el !== document.body) {
    const cs = getComputedStyle(el);
    const oy = cs.overflowY;
    const scrollable = oy === "auto" || oy === "scroll";
    if (
      scrollable &&
      el.scrollHeight > el.clientHeight &&
      el.clientHeight > 200 &&
      el.clientWidth > 300
    ) {
      return el;
    }
    el = el.parentElement;
  }
  return null;
}

// Replace your existing getChatRoot() with this
function getChatRoot() {
  // [NEW] Prefer explicit per-thread container (e.g., Messenger)
  const explicit = document.querySelector(
    '[aria-label^="Messages in conversation with "]'
  );
  if (explicit) return explicit;

  const composer = document.querySelector(
    'main [contenteditable="true"], [role="textbox"], textarea'
  );
  if (composer) {
    const pane = findScrollParent(composer);
    if (pane) return pane;
  }
  const fallbacks = [
    'main [role="main"] [role="list"]',
    'main [role="main"] [data-testid*="scroll"]',
    'main [role="main"] article',
    '[role="main"] [role="log"]',
    '#main div[role="region"]',
  ];
  for (const sel of fallbacks) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return document.querySelector(AD.containerSelector) || document.body;
}

function getMessageNodes() {
  const root = getChatRoot();
  const composerR = getComposerRect();
  const all = Array.from(root.querySelectorAll("*")).filter((el) => {
    if (!el || el.id === "qrizz-lite") return false;
    const role = (el.getAttribute?.("role") || "").toLowerCase();
    if (role === "textbox" || el.isContentEditable) return false;
    const txt = (el.innerText || el.textContent || "").trim();
    if (!txt || txt.length < 2) return false;
    const cs = getComputedStyle(el);
    if (
      cs.display === "none" ||
      cs.visibility === "hidden" ||
      +cs.opacity === 0
    )
      return false;
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 12) return false;
    if (r.bottom < 0 || r.top > (window.innerHeight || 0)) return false;
    if (composerR && r.top >= composerR.top - 8) return false;
    if (cs.position === "fixed" && r.top < 120) return false;
    return true;
  });
  const dens = (e) =>
    (e.innerText || e.textContent || "").replace(/\s+/g, "").length;
  const scored = all.map((e) => {
    const b = toBubble(e);
    const r = b.getBoundingClientRect();
    const isBubble = b.matches?.(
      '[role="listitem"], [role="row"], article, li, [data-testid*="message"]'
    );
    const score = r.bottom + (isBubble ? 2000 : 0) + Math.min(300, dens(b));
    return { el: b, score };
  });
  const uniq = [];
  const seen = new Set();
  for (const it of scored.sort((a, b) => a.score - b.score)) {
    const key = it.el;
    if (!seen.has(key)) {
      seen.add(key);
      uniq.push(it.el);
    }
  }
  return uniq
    .slice(-20)
    .filter(
      (e) => (e.innerText || e.textContent || "").replace(/\s+/g, "").length > 4
    );
}
function guessRole(el) {
  try {
    const node = toBubble(el);
    const al = (node.getAttribute?.("aria-label") || "").toLowerCase();
    if (al.includes("you")) return "you";
    if (node.closest?.('[data-owner="self"]')) return "you";
    const row = node.closest('[role="listitem"]') || node.parentElement || node;
    const s = getComputedStyle(row);
    const ta = s.textAlign || "";
    if (ta === "end" || ta === "right") return "you";
  } catch {}
  return "them";
}

/* ---------------- BG relay ---------------- */
function askBackend(type, body) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type, body }, (resp) => {
      resolve(resp || { ok: false, status: 0, error: "no response" });
    });
  });
}

/* ---------------- UI ---------------- */
const chipBoxCSS = `display:flex;align-items:center;gap:6px;margin:2px;
  padding:10px 12px;border:1px solid #e5e7eb;border-radius:12px;background:#fff;
  color:#111;cursor:pointer;user-select:none;box-shadow:0 2px 6px rgba(0,0,0,.08);
  transition:transform .12s ease, filter .12s ease`;
const textCSS = `display:inline-block;max-width:34vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600;letter-spacing:.2px`;
const btnCSS = `border:none;background:transparent;cursor:pointer;font-size:14px;line-height:1;padding:2px 4px`;

function headerHTML(heat, stage, spiceDbg) {
  const idx = Math.max(0, Math.min(3, Number(heat) || 1));
  const label = ["H0", "H1", "H2", "H3"][idx];
  const color = ["#6b7280", "#2563eb", "#f59e0b", "#ef4444"][idx];
  const stageTxt = (stage ? String(stage) : "UNKNOWN").toUpperCase();

  const root = overlay();
  const heatPill = root.querySelector("#qr-heat-pill");
  const stagePill = root.querySelector("#qr-stage-pill");
  if (heatPill) {
    heatPill.innerHTML = `🔥 ${label}`;
    heatPill.style.color = color;
    heatPill.style.borderColor = color;
  }
  if (stagePill) {
    stagePill.textContent = `📍 ${stageTxt}`;
  }

  return `
    <div style="display:none">legacy-header</div>
    <div id="qr-grid"></div>
  `;
}
function setStatus(txt) {
  const s = bodyEl().querySelector("#qr-status");
  if (s) s.textContent = txt || "";
  const loading = bodyEl().querySelector("#qr-loading");
  const grid = bodyEl().querySelector("#qr-grid");
  const isThinking = (txt || "").toLowerCase().includes("thinking");
  if (loading && grid) {
    if (isThinking) {
      grid.style.display = "none";
      loading.style.display = "flex";
    } else {
      loading.style.display = "none";
      grid.style.display = "flex";
      if ((txt || "").toLowerCase() === "ready") {
        spawnHeatEmojis(window.__qr_spice || 1);
      }
    }
  }
}

/* --- outline analyzed messages --- */
let __hiBoxes = [];
function clearOutlines() {
  for (const b of __hiBoxes) b.remove();
  __hiBoxes.length = 0;
}
function drawOutlines(nodes) {
  //  guard to disable outlines entirely
  if (!SHOW_SCAN_OUTLINE) {
    clearOutlines();
    return;
  }
  clearOutlines();
  nodes.forEach((el) => {
    const r = el.getBoundingClientRect();
    const box = document.createElement("div");
    Object.assign(box.style, {
      position: "fixed",
      left: `${r.left}px`,
      top: `${r.top}px`,
      width: `${r.width}px`,
      height: `${r.height}px`,
      border: "2px solid rgba(37,99,235,0.85)",
      borderRadius: "10px",
      background: "rgba(37,99,235,0.08)",
      zIndex: 2147483646,
      pointerEvents: "none",
    });
    document.documentElement.appendChild(box);
    __hiBoxes.push(box);
  });
  setTimeout(clearOutlines, 1200);
}

/* ---------------- Suggest flow ---------------- */
let inFlight = false,
  lastCall = 0,
  lastRendered = { heat: null, stage: null, options: [] };

function bindStaticHandlersOnce() {
  const root = bodyEl();
  if (root.dataset.handlers === "1") return;
  root.dataset.handlers = "1";

  root.addEventListener(
    "click",
    async (e) => {
      const chip = e.target.closest(".qr-chip");
      if (!chip) return;
      e.preventDefault();
      e.stopPropagation();

      const idx = Number(chip.dataset.i) || 0;
      const options = lastRendered.options || [];
      const text = String(options[idx] || "");
      if (!text) return;

      if (
        e.target.classList.contains("qr-up") ||
        e.target.classList.contains("qr-down")
      ) {
        const label = e.target.classList.contains("qr-up") ? "up" : "down";
        askBackend("qr_feedback", {
          stage: window.__qr_stage || "banter",
          latest: window.__qr_latest || "",
          option: text,
          label,
          meta: {
            site: location.hostname,
            thread: getThreadId(),
            history_len: ctx.length,
            index: idx,
          },
        }).then(() => showToast("Noted"));

        const rating = e.target.classList.contains("qr-up") ? "Y" : "N";
        if (
          window.__qr_pending &&
          window.__qr_pending.options &&
          window.__qr_pending.options[idx]
        ) {
          window.__qr_pending.options[idx].rating = rating;
        }
        askBackend("qr_commit", {
          text: window.__qr_latest || "",
          stage: window.__qr_stage || "banter",
          heat: window.__qr_spice || 1,
          options: [{ text, rating }],
        });
        return;
      }

      if (
        e.target.classList.contains("qr-text") ||
        e.target.closest(".qr-text")
      ) {
        await copyText(text);
        askBackend("qr_feedback", {
          stage: window.__qr_stage || "banter",
          latest: window.__qr_latest || "",
          option: text,
          label: "clicked",
          meta: {
            site: location.hostname,
            thread: getThreadId(),
            history_len: ctx.length,
            index: idx,
          },
        }).catch(() => {});
        return;
      }
    },
    { passive: false }
  );

  const rootEl = overlay();
  const commitBtn = rootEl.querySelector("#qr-commit");
  const resetBtn = rootEl.querySelector("#qr-reset");
  [commitBtn, resetBtn].forEach((b) => {
    if (!b) return;
    b.addEventListener(
      "mouseenter",
      () => (b.style.transform = "translateY(-1px) scale(1.02)")
    );
    b.addEventListener(
      "mouseleave",
      () => (b.style.transform = "translateY(0) scale(1)")
    );
    b.addEventListener(
      "mousedown",
      () => (b.style.transform = "translateY(0) scale(0.98)")
    );
    b.addEventListener(
      "mouseup",
      () => (b.style.transform = "translateY(-1px) scale(1.02)")
    );
  });

  root.addEventListener("click", (e) => {
    if (e.target.id === "qr-reset") {
      e.preventDefault();
      e.stopPropagation();
      ctx = [];
      saveCtx(ctx);
      lastSeenText = "";
      lastSeenRole = "";
      showToast("Context reset");
    }
  });

  root.addEventListener("click", (e) => {
    if (e.target.id === "qr-commit") {
      e.preventDefault();
      e.stopPropagation();
      commitSnapshot(window.__qr_pending);
    }
  });
}

function renderStatic(heat, stage, options, spiceDbg) {
  const panel = bodyEl();
  const grid = panel.querySelector("#qr-grid");
  const loading = panel.querySelector("#qr-loading");

  loading.style.display = "none";
  grid.style.display = "flex";

  headerHTML(heat, stage, spiceDbg);

  const chips = options
    .map(
      (o, i) => `
      <div class="qr-chip" data-i="${i}" style="${chipBoxCSS}">
        <span class="qr-text" style="${textCSS}">${String(o)}</span>
        <div style="display:flex;align-items:center;gap:6px;margin-left:6px;">
          <button class="qr-up"   data-i="${i}" title="Good" style="${btnCSS}">👍</button>
          <button class="qr-down" data-i="${i}" title="Bad"  style="${btnCSS}">👎</button>
        </div>
      </div>
    `
    )
    .join("");
  grid.innerHTML =
    chips || "<span style='color:#000;margin:6px;'>— no suggestion —</span>";
  bindStaticHandlersOnce();
  lastRendered = { heat, stage, options: options.slice() };
}

// --- ensure history ends with 'them' before sending ---
function trimTailToThem(arr) {
  const copy = sanitizeCtx(arr).slice();
  while (copy.length && copy[copy.length - 1].role === "you") copy.pop();
  return copy;
}

async function requestSuggestions(curCtx) {
  const now = Date.now();
  if (inFlight || now - lastCall < COOLDOWN) return;
  inFlight = true;
  lastCall = now;
  setStatus("thinking…");
  try {
    const nodes = getMessageNodes();
    drawOutlines(nodes);

    const ctxTrim = trimTailToThem(curCtx);
    if (!ctxTrim.length || ctxTrim[ctxTrim.length - 1].role !== "them") {
      setStatus("idle");
      return;
    }

    const payload = {
      context: ctxTrim
        .slice(-MAX_TURNS)
        .map(({ role, text }) => ({ role, text })),
      n: 3,
    };
    const resp = await askBackend("qr_suggest", payload);
    const json = (resp && resp.data) || {};
    const options = Array.isArray(json.options) ? json.options : [];
    window.__qr_stage = json.stage || "banter";
    window.__qr_spice = typeof json.spice === "number" ? json.spice : 1;
    window.__qr_latest =
      (
        ctxTrim
          .slice()
          .reverse()
          .find((m) => m.role === "them") || {}
      ).text || "";
    window.__qr_debug = json.debug || {};

    window.__qr_pending = makeSnapshot(
      window.__qr_latest,
      window.__qr_stage,
      window.__qr_spice,
      options
    );

    if (window.__qr_debug && window.__qr_debug.spice) {
      console.debug("[QuickRizz][spice]", window.__qr_debug.spice);
    }

    const changed =
      lastRendered.heat !== window.__qr_spice ||
      lastRendered.stage !== window.__qr_stage ||
      options.join("||") !== (lastRendered.options || []).join("||");
    if (changed)
      renderStatic(
        window.__qr_spice,
        window.__qr_stage,
        options,
        window.__qr_debug.spice
      );
    setStatus(options.length ? "ready" : "idle");
  } catch (e) {
    console.debug("[QuickRizz] request error", e);
    setStatus("error");
  } finally {
    inFlight = false;
  }
}

/* ---------------- Tick loop ---------------- */
function pushTurn(arr, role, text) {
  const t = clamp(text);
  if (!t) return sanitizeCtx(arr);
  const next = Array.isArray(arr) ? arr.slice() : [];
  next.push({ role, text: t, ts: Date.now() });
  return sanitizeCtx(next);
}
function readLatest() {
  const list = getMessageNodes();
  if (!list.length) return null;
  const el = list[list.length - 1];
  const bubble = toBubble(el);
  const text = clamp(bubble.innerText || bubble.textContent || "");
  const role = guessRole(bubble);
  return { el: bubble, text, role };
}

let _stableTimer = null;
let _lastIncomingCommitted = "";

function tick() {
  try {
    maybeThreadRotate();
    const latest = readLatest();
    if (!latest || !latest.text) return;

    if (latest.text !== lastSeenText) {
      if (softResetIfNewConversation(latest, ctx)) {
        lastSeenText = latest.text;
        lastSeenRole = latest.role;
        return;
      }
      ctx = pushTurn(ctx, latest.role, latest.text);
      saveCtx(ctx);
      lastSeenText = latest.text;
      lastSeenRole = latest.role;
    }

    if (latest.role !== "them" && !TEST_MODE) return;
    if (latest.text === _lastIncomingCommitted && !TEST_MODE) return;

    clearTimeout(_stableTimer);
    const snapshotText = latest.text;
    _stableTimer = setTimeout(() => {
      const again = readLatest();
      if (!again || !again.text) return;
      if ((again.role !== "them" && !TEST_MODE) || again.text !== snapshotText)
        return;

      const ctxTrim = trimTailToThem(ctx);
      if (!ctxTrim.length || ctxTrim[ctxTrim.length - 1].role !== "them")
        return;

      _lastIncomingCommitted = snapshotText;
      requestSuggestions(ctxTrim);
    }, 450);
  } catch (e) {
    console.debug("[QuickRizz] tick error:", e);
  }
}
setInterval(tick, 1000);

/* ---------------- Boot ---------------- */
if (!bodyEl().innerHTML) {
  overlay();
  setStatus("idle");
  setTimeout(() => {
    const bootTrim = trimTailToThem(ctx);
    if (
      bootTrim.length &&
      (bootTrim[bootTrim.length - 1].role === "them" || TEST_MODE)
    ) {
      requestSuggestions(bootTrim);
    }
  }, 50);
}
