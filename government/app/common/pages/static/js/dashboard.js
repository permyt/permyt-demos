/* Government dashboard: profile save + websocket request feed */

(function () {
  "use strict";

  // ── CSRF helper ──────────────────────────────────────────────────
  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  // ── Profile form submit ──────────────────────────────────────────
  const form = document.getElementById("profile-form");
  const status = document.getElementById("profile-status");

  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      const submitBtn = form.querySelector(".save-btn");
      submitBtn.disabled = true;
      const original = submitBtn.textContent;
      submitBtn.textContent = "Saving…";
      status.textContent = "";
      status.className = "save-status";

      const payload = {};
      new FormData(form).forEach((value, key) => {
        payload[key] = typeof value === "string" ? value.trim() : value;
      });
      // Empty date fields must be sent as null, not "".
      ["birthdate", "incorporation_date"].forEach(function (k) {
        if (payload[k] === "") payload[k] = null;
      });
      // Beneficial owners arrive as a JSON string from the stakeholders editor;
      // promote it to a real array the API can sync.
      if (payload.shareholders_json !== undefined) {
        try {
          payload.shareholders = JSON.parse(payload.shareholders_json || "[]");
        } catch (_) {
          payload.shareholders = [];
        }
        delete payload.shareholders_json;
      }

      try {
        const resp = await fetch("/rest/profile/", {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify(payload),
        });

        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          status.textContent = (data && (data.detail || JSON.stringify(data))) || "Error";
          status.className = "save-status error";
        } else {
          const data = await resp.json();
          // Reflect any normalisation (uppercased country, trimmed values).
          Object.entries(data).forEach(([k, v]) => {
            const el = form.querySelector('[name="' + k + '"]');
            if (el && v !== null && v !== undefined) el.value = v;
          });
          status.textContent = "Saved";
          status.className = "save-status saved";
          setTimeout(function () {
            status.textContent = "";
            status.className = "save-status";
          }, 2000);
        }
      } catch (err) {
        status.textContent = err.message;
        status.className = "save-status error";
      }

      submitBtn.disabled = false;
      submitBtn.textContent = original;
    });
  }

  // ── Request bubble helpers ───────────────────────────────────────
  const logPanel = document.getElementById("log-panel");
  const clearBtn = document.getElementById("clearLogBtn");

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function renderBubble(el, { scopes, action, success, updatedAt }) {
    el.className = "request-bubble " + (success ? "ok" : "fail");

    let html = '<div class="bubble-scopes">' + escapeHtml((scopes || []).join(", ")) + "</div>";
    html += '<div class="bubble-status">';
    html += '<span class="status-text">' + escapeHtml(action || "update") + "</span>";
    html += '<span class="entry-time">' + escapeHtml(updatedAt || new Date().toLocaleTimeString("en-GB")) + "</span>";
    html += '<span class="badge ' + (success ? "success" : "error") + '">' + (success ? "OK" : "FAIL") + "</span>";
    html += "</div>";

    el.innerHTML = html;
  }

  function upsertBubble(requestId, data) {
    const empty = document.getElementById("empty-state");
    if (empty) empty.remove();

    let el = requestId ? logPanel.querySelector('[data-request-id="' + requestId + '"]') : null;
    if (!el) {
      el = document.createElement("div");
      if (requestId) el.dataset.requestId = requestId;
    }

    renderBubble(el, data);
    logPanel.prepend(el);
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", async function () {
      try {
        await fetch("/rest/logs/clear/", {
          method: "POST",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
        });
      } catch (_) {
        // best-effort — still wipe the DOM
      }
      logPanel.innerHTML = '<p class="empty-state" id="empty-state">No requests yet.</p>';
    });
  }

  // ── WebSocket ────────────────────────────────────────────────────
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(protocol + "//" + window.location.host + "/ws/");
  let pingInterval;

  ws.addEventListener("open", function () {
    pingInterval = setInterval(function () {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
  });

  ws.addEventListener("message", function (e) {
    try {
      const msg = JSON.parse(e.data);
      if (msg.model === "Log" || msg.type === "notify") {
        const d = msg.data || msg;
        const fields = d.fields || {};
        const logData = fields.data || d.data || {};

        upsertBubble(logData.permyt_request_id || fields.permyt_request_id || null, {
          scopes: logData.scopes || [],
          action: fields.action || d.action || "update",
          success: fields.success !== undefined ? fields.success : true,
          updatedAt: new Date().toLocaleTimeString("en-GB"),
        });
      }
    } catch (_) {
      // ignore non-JSON messages
    }
  });

  ws.addEventListener("close", function () {
    clearInterval(pingInterval);
  });
})();
