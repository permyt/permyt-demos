/**
 * Age-verification client.
 *
 * Listens on the per-session WebSocket for events emitted by PermytClient
 * (`scanned`, `awaiting_approval`, `verifying`, `verified`, `verification_failed`),
 * drives the stage track, and swaps to a success or error pane when the
 * broker returns a terminal status. The "Verify again" button resets state
 * and asks the server for a fresh QR.
 */
(function () {
  const cfg = window.__verify || {};
  const $ = (id) => document.getElementById(id);

  const csrfToken = (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";

  const qrPane = document.querySelector('[data-pane="qr"]');
  const resultPane = document.querySelector('[data-pane="result"]');
  const errorPane = document.querySelector('[data-pane="error"]');
  const qrStatus = $("qr-status");
  const qrContainer = $("qr-container");
  const stageTrack = document.querySelector("[data-stage-track]");
  const stageSteps = stageTrack
    ? Array.from(stageTrack.querySelectorAll(".stage-step"))
    : [];
  const errorReason = $("error-reason");
  const resetBtn = $("resetBtn");
  const retryBtn = $("retryBtn");

  const STAGE_ORDER = ["scan", "awaiting", "verifying", "done"];

  // ── Pane swap ──────────────────────────────────────────────────────
  function showPane(name) {
    [qrPane, resultPane, errorPane].forEach((pane) => {
      if (!pane) return;
      const isTarget =
        (name === "qr" && pane === qrPane) ||
        (name === "result" && pane === resultPane) ||
        (name === "error" && pane === errorPane);
      pane.setAttribute("data-state", isTarget ? "visible" : "hidden");
      pane.setAttribute("aria-hidden", isTarget ? "false" : "true");
    });
    if (window.lucide) window.lucide.createIcons();
  }

  // ── Stage track ────────────────────────────────────────────────────
  function setStage(name) {
    const idx = STAGE_ORDER.indexOf(name);
    if (idx < 0) return;
    stageSteps.forEach((step) => {
      const stepName = step.dataset.stage;
      const stepIdx = STAGE_ORDER.indexOf(stepName);
      step.classList.remove("pending", "active", "done", "error");
      if (name === "done") {
        step.classList.add("done");
      } else if (stepIdx < idx) {
        step.classList.add("done");
      } else if (stepIdx === idx) {
        step.classList.add("active");
      } else {
        step.classList.add("pending");
      }
    });
  }

  function setStageError(name, reason) {
    const idx = STAGE_ORDER.indexOf(name);
    stageSteps.forEach((step, i) => {
      step.classList.remove("active", "pending", "done", "error");
      if (i < idx) step.classList.add("done");
      else if (i === idx) step.classList.add("error");
      else step.classList.add("pending");
    });
    setQrStatus(reason || "Verification failed.", "error");
  }

  function setQrStatus(text, cls) {
    if (!qrStatus) return;
    qrStatus.textContent = text || "";
    qrStatus.className = "qr-status " + (cls || "");
  }

  // ── QR auto-refresh ────────────────────────────────────────────────
  let qrRefreshTimer = null;

  function scheduleQrRefresh(ttlSeconds) {
    if (qrRefreshTimer) clearTimeout(qrRefreshTimer);
    const ttl = (ttlSeconds || 300) * 1000;
    const lead = Math.min(30000, Math.max(5000, Math.floor(ttl * 0.1)));
    qrRefreshTimer = setTimeout(refreshQr, ttl - lead);
  }

  function stopQrRefresh() {
    if (qrRefreshTimer) {
      clearTimeout(qrRefreshTimer);
      qrRefreshTimer = null;
    }
  }

  async function refreshQr() {
    try {
      const res = await fetch("/rest/verification/qr/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        if (res.status === 409) return;
        scheduleQrRefresh(30);
        return;
      }
      const data = await res.json();
      if (data.qr_svg && qrContainer) qrContainer.innerHTML = data.qr_svg;
      scheduleQrRefresh(data.ttl_seconds);
    } catch (_) {
      scheduleQrRefresh(30);
    }
  }

  // ── Reset / verify again ───────────────────────────────────────────
  async function resetVerification() {
    stopQrRefresh();
    try {
      const res = await fetch("/rest/verification/reset/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        window.location.reload();
        return;
      }
      const data = await res.json();
      if (data.qr_svg && qrContainer) qrContainer.innerHTML = data.qr_svg;
      setStage("scan");
      setQrStatus("Waiting for scan");
      showPane("qr");
      scheduleQrRefresh(data.ttl_seconds);
    } catch (_) {
      window.location.reload();
    }
  }

  if (resetBtn) resetBtn.addEventListener("click", resetVerification);
  if (retryBtn) retryBtn.addEventListener("click", resetVerification);

  // ── Initial state from server ──────────────────────────────────────
  if (cfg.isVerified) {
    setStage("done");
    showPane("result");
  } else {
    setStage("scan");
    showPane("qr");
    scheduleQrRefresh();
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  function openSocket() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + window.location.host + "/ws/");
    ws.addEventListener("message", (msg) => {
      let payload;
      try { payload = JSON.parse(msg.data); } catch (_) { return; }
      switch (payload.event) {
        case "scanned":
          stopQrRefresh();
          setStage("awaiting");
          setQrStatus("Scanned — approve on PERMYT.", "info");
          break;
        case "awaiting_approval":
          setStage("awaiting");
          setQrStatus("Approve the check on your PERMYT app.", "info");
          break;
        case "verifying":
          setStage("verifying");
          setQrStatus("Verifying…", "info");
          break;
        case "verified":
          setStage("done");
          setQrStatus("Verified.", "ok");
          setTimeout(() => showPane("result"), 350);
          break;
        case "verification_failed":
          if (errorReason) {
            errorReason.textContent = payload.reason || "Please try again.";
          }
          const active = stageSteps.find((s) => s.classList.contains("active"));
          setStageError(active ? active.dataset.stage : "verifying", payload.reason);
          setTimeout(() => showPane("error"), 350);
          break;
        case "status":
          break;
        default:
          break;
      }
    });
    ws.addEventListener("close", () => setTimeout(openSocket, 1500));
  }
  openSocket();
})();
