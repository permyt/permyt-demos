/* NoteVault dashboard: field saving, add/delete, websocket request feed */

(function () {
  "use strict";

  // ── CSRF helper ──────────────────────────────────────────────────
  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }

  // ── Bind save/delete on a note-card ──────────────────────────────
  function bindCard(card) {
    const field = card.dataset.field;
    const textarea = card.querySelector(".note-textarea");
    const btn = card.querySelector(".save-btn");
    const status = card.querySelector(".save-status");

    btn.addEventListener("click", async function () {
      btn.disabled = true;
      btn.textContent = "Saving…";
      status.textContent = "";
      status.className = "save-status";

      try {
        const resp = await fetch("/rest/notes/" + field + "/", {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify({ content: textarea.value }),
        });

        if (!resp.ok) {
          const data = await resp.json();
          status.textContent = data.error || "Error";
          status.className = "save-status error";
        } else {
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

      btn.disabled = false;
      btn.textContent = "Save";
    });

    // Delete button (superuser only)
    const delBtn = card.querySelector(".delete-btn");
    if (delBtn) {
      delBtn.addEventListener("click", async function () {
        if (!confirm("Delete field '" + field + "'? This removes it for all users.")) return;

        try {
          const resp = await fetch("/rest/notes/" + field + "/", {
            method: "DELETE",
            headers: { "X-CSRFToken": getCookie("csrftoken") },
          });
          if (resp.ok || resp.status === 204) {
            card.remove();
          } else {
            const data = await resp.json();
            alert(data.error || "Failed to delete field.");
          }
        } catch (err) {
          alert(err.message);
        }
      });
    }
  }

  // ── Bind all existing cards ──────────────────────────────────────
  document.querySelectorAll(".note-card").forEach(bindCard);

  // ── Add field (superuser only) ───────────────────────────────────
  const addBtn = document.getElementById("add-field-btn");
  if (addBtn) {
    const nameInput = document.getElementById("new-field-name");
    const addStatus = document.getElementById("add-field-status");

    addBtn.addEventListener("click", async function () {
      const name = nameInput.value.trim();
      if (!name) return;

      addBtn.disabled = true;
      addStatus.textContent = "";
      addStatus.className = "save-status";

      try {
        const resp = await fetch("/rest/notes/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken"),
          },
          body: JSON.stringify({ name: name }),
        });

        const data = await resp.json();
        if (!resp.ok) {
          addStatus.textContent = data.error || "Error";
          addStatus.className = "save-status error";
        } else {
          // Reload to show the new field with its seeded value
          window.location.reload();
        }
      } catch (err) {
        addStatus.textContent = err.message;
        addStatus.className = "save-status error";
      }

      addBtn.disabled = false;
    });
  }

  // ── Clear logs ────────────────────────────────────────────────────
  const clearBtn = document.getElementById("clearLogBtn");

  // ── Request bubble helpers ───────────────────────────────────────
  const logPanel = document.getElementById("log-panel");

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
