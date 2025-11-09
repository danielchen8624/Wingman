// bg.js — relay fetches to bypass page CSP
const API = "http://127.0.0.1:8000";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "qr_suggest") {
    (async () => {
      try {
        const r = await fetch(`${API}/suggest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg.body || {})
        });
        const data = await r.json().catch(() => ({}));
        sendResponse({ ok: r.ok, status: r.status, data });
      } catch (e) {
        sendResponse({ ok: false, status: 0, data: { error: String(e) } });
      }
    })();
    return true; // keep channel open
  }

  if (msg?.type === "qr_feedback") {
    (async () => {
      try {
        const r = await fetch(`${API}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg.body || {})
        });
        const data = await r.json().catch(() => ({}));
        sendResponse({ ok: r.ok, status: r.status, data });
      } catch (e) {
        sendResponse({ ok: false, status: 0, data: { error: String(e) } });
      }
    })();
    return true;
  }

  if (msg?.type === "qr_commit") {
    (async () => {
      try {
        const r = await fetch(`${API}/commit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(msg.body || {})
        });
        let data = {};
        try { data = await r.json(); } catch {
          try { data = { error: await r.text() }; } catch {}
        }
        sendResponse({ ok: r.ok, status: r.status, data });
      } catch (e) {
        sendResponse({ ok: false, status: 0, data: { error: String(e) } });
      }
    })();
    return true;
  }
});
