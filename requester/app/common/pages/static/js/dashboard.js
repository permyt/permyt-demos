/* Dashboard: chat-style request feed + websocket status updates */

(function () {
  "use strict";

  // ── helpers ──────────────────────────────────────────────────────
  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function cssEscape(s) {
    if (window.CSS && CSS.escape) return CSS.escape(s);
    return String(s).replace(/"/g, '\\"');
  }

  // ── DOM ──────────────────────────────────────────────────────────
  const form = document.getElementById("requestForm");
  const btn = document.getElementById("submitBtn");
  const descriptionInput = document.getElementById("description");
  const feed = document.getElementById("feed");
  const clearBtn = document.getElementById("clearLogBtn");

  // Enter submits, Shift+Enter inserts a newline.
  descriptionInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    }
  });

  // ── Feed operations ──────────────────────────────────────────────
  function removeEmptyState() {
    const empty = document.getElementById("empty-state");
    if (empty) empty.remove();
  }

  function renderBubble(bubble, { description, status, success, updatedAt, responses }) {
    bubble.className = "request-bubble " + (success ? "ok" : "fail");
    const time = updatedAt || new Date().toLocaleTimeString("en-GB");
    let html = "";
    if (description !== undefined) {
      html += '<div class="bubble-description">' + escapeHtml(description) + "</div>";
    } else {
      const existing = bubble.querySelector(".bubble-description");
      html += existing ? existing.outerHTML : "";
    }
    html += '<div class="bubble-status">'
      + '<span class="status-text">' + escapeHtml(status || "updated") + "</span>"
      + '<span class="entry-time">' + escapeHtml(time) + "</span>"
      + '<span class="badge ' + (success ? "success" : "error") + '">'
      + (success ? "OK" : "FAIL") + "</span>"
      + "</div>";
    if (Array.isArray(responses) && responses.length) {
      const payload = responses.length === 1 ? responses[0] : responses;
      const pretty = JSON.stringify(payload, null, 2);
      html += '<pre class="bubble-preview">' + escapeHtml(pretty) + "</pre>";
    }
    bubble.innerHTML = html;
  }

  function upsertBubble(requestId, payload) {
    if (!requestId) return;
    removeEmptyState();
    let bubble = feed.querySelector('[data-request-id="' + cssEscape(requestId) + '"]');
    if (!bubble) {
      bubble = document.createElement("div");
      bubble.setAttribute("data-request-id", requestId);
      feed.prepend(bubble);
    } else {
      feed.prepend(bubble);
    }
    renderBubble(bubble, payload);
  }

  // ── Form submission ──────────────────────────────────────────────
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const description = descriptionInput.value.trim();
    if (!description) return;

    btn.disabled = true;
    btn.textContent = "Sending…";

    try {
      const resp = await fetch("/rest/requests/submit/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ description }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        const msg = data.message || data.error || "Request failed";
        upsertBubble("error-" + Date.now(), {
          description,
          status: msg,
          success: false,
        });
      } else if (data.request_id) {
        upsertBubble(data.request_id, {
          description: data.description || description,
          status: data.status || "queued",
          success: true,
        });
        descriptionInput.value = "";
      }
    } catch (err) {
      upsertBubble("error-" + Date.now(), {
        description,
        status: err.message,
        success: false,
      });
    }

    btn.disabled = false;
    btn.textContent = "Send";
    descriptionInput.focus();
  });

  // ── Clear ────────────────────────────────────────────────────────
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
      feed.innerHTML = '<p class="empty-state" id="empty-state">No requests yet.</p>';
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
      if (msg.model !== "Log") return;

      const rows = Array.isArray(msg.data) ? msg.data : [msg.data];
      for (const row of rows) {
        if (!row) continue;
        const fields = row.fields || row;
        const requestId = fields.permyt_request_id;
        if (!requestId) continue;

        const logData = fields.data || {};
        upsertBubble(requestId, {
          description: logData.description,
          status: logData.status || fields.action || "updated",
          success: fields.success !== false,
          responses: logData.responses,
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
