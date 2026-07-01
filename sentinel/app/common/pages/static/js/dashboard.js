/* Sentinel dashboard: screening toggles + websocket request feed */

(function () {
  "use strict";

  // ── CSRF helper ──────────────────────────────────────────────────
  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  const status = document.getElementById("profile-status");

  function flash(text, cls) {
    if (!status) return;
    status.textContent = text;
    status.className = "save-status " + (cls || "");
    if (cls === "saved") {
      setTimeout(function () {
        status.textContent = "";
        status.className = "save-status";
      }, 1800);
    }
  }

  // ── Screening toggles — PUT one field at a time ──────────────────
  function reflectResult(field, flagged) {
    const chip = document.querySelector('[data-result-for="' + field + '"]');
    if (!chip) return;
    chip.dataset.flagged = flagged ? "true" : "false";
    chip.innerHTML = '<span class="dot"></span>' + (flagged ? "Yes" : "No");
  }

  document.querySelectorAll(".screening-toggle").forEach(function (toggle) {
    toggle.addEventListener("change", async function () {
      const field = toggle.dataset.field;
      const value = toggle.checked;
      const payload = {};
      payload[field] = value;

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
          toggle.checked = !value; // revert
          flash("Error", "error");
          return;
        }
        const data = await resp.json();
        reflectResult(field, !!data[field]);
        flash("Saved", "saved");
      } catch (err) {
        toggle.checked = !value; // revert
        flash("Error", "error");
      }
    });
  });

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
      logPanel.innerHTML = '<p class="empty-state" id="empty-state">No access requests yet.</p>';
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
