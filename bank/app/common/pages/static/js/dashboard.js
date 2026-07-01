/* Meridian dashboard: WebSocket-driven balance + movements refresh.
   The account-holder name and address are gov-verified via PERMYT and
   rendered as static, non-editable text — there is no edit/save path here. */

(function () {
  "use strict";

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  // ── Refresh helpers ──────────────────────────────────────────────
  function fmtAmountClass(amount) {
    return String(amount).trim().startsWith("-") ? "debit" : "credit";
  }

  function renderMovement(m) {
    const li = document.createElement("li");
    const cls = fmtAmountClass(m.amount);
    li.className = "movement " + cls;
    li.dataset.id = m.id;

    const icon = document.createElement("span");
    icon.className = "movement-icon";
    const i = document.createElement("i");
    i.setAttribute("data-lucide", cls === "debit" ? "arrow-up-right" : "arrow-down-left");
    icon.appendChild(i);
    li.appendChild(icon);

    const main = document.createElement("div");
    main.className = "movement-main";
    main.innerHTML =
      '<div class="movement-counterparty">' +
      escapeHtml(m.counterparty_name || m.counterparty_iban) +
      '</div>' +
      '<div class="movement-reference">' +
      escapeHtml(m.reference || "") +
      '</div>';

    const side = document.createElement("div");
    side.className = "movement-side";
    side.innerHTML =
      '<div class="movement-amount">' +
      escapeHtml(m.amount) + " " + escapeHtml(m.currency) +
      '</div>' +
      '<div class="movement-date">' +
      escapeHtml(m.date || "") +
      '</div>';

    li.appendChild(main);
    li.appendChild(side);
    return li;
  }

  async function refreshMovements() {
    try {
      const resp = await fetch("/rest/movements/", {
        headers: { Accept: "application/json" },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      const list = document.getElementById("movements-list");
      if (!list) return;
      list.innerHTML = "";
      const movements = (data && data.movements) || [];
      if (!movements.length) {
        const empty = document.createElement("li");
        empty.id = "movements-empty";
        empty.className = "movement empty";
        empty.textContent = "No movements yet.";
        list.appendChild(empty);
        return;
      }
      movements.forEach(function (m) {
        list.appendChild(renderMovement(m));
      });
      if (window.lucide) window.lucide.createIcons();
    } catch (_) {
      // best-effort
    }
  }

  // ── WebSocket — listen for balance_changed pushes ────────────────
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
      if (!msg) return;
      if (msg.type === "balance_changed") {
        const amountEl = document.getElementById("balance-amount");
        const ccyEl = document.getElementById("balance-currency");
        if (amountEl && msg.balance !== undefined) amountEl.textContent = msg.balance;
        if (ccyEl && msg.currency) ccyEl.textContent = msg.currency;
        refreshMovements();
      }
    } catch (_) {
      // ignore non-JSON messages
    }
  });

  ws.addEventListener("close", function () {
    clearInterval(pingInterval);
  });
})();
