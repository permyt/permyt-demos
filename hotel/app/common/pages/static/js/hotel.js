/**
 * Hotel check-in client.
 *
 * Listens on the per-session WebSocket for events emitted by PermytClient
 * (`scanned`, `form_filled`, `paid`, `*_failed`), drives the QR stage track,
 * staggers identity-field reveal, and animates the pay overlay.
 */
(function () {
  const cfg = window.__hotel || {};
  const $ = (id) => document.getElementById(id);

  const csrfToken = (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";

  const fields = ["full_name", "address", "country", "vat"];
  const inputs = Object.fromEntries(fields.map((f) => [f, $("field-" + f)]));
  const nightsSel = $("field-nights");
  const totalEl = $("total-display");
  const payBtn = $("payBtn");
  const payAmount = $("pay-amount");
  const payOverlayAmount = $("pay-overlay-amount");
  const formStatus = $("form-status");
  const qrStatus = $("qr-status");
  const qrContainer = $("qr-container");
  const stageTrack = document.querySelector("[data-stage-track]");
  const stageSteps = stageTrack
    ? Array.from(stageTrack.querySelectorAll(".stage-step"))
    : [];
  const payOverlay = $("payOverlay");
  const payTrack = document.querySelector("[data-pay-track]");
  const paySteps = payTrack
    ? Array.from(payTrack.querySelectorAll(".pay-step"))
    : [];
  const payOverlayStatus = $("pay-overlay-status");

  let currentTotalDisplay = "";
  let phase = "identity"; // 'identity' | 'payment'

  // ── Nights selector (1..14) ──────────────────────────────────────
  const current = parseInt(nightsSel.dataset.current || "1", 10);
  for (let n = 1; n <= 14; n++) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = n + (n === 1 ? " night" : " nights");
    if (n === current) opt.selected = true;
    nightsSel.appendChild(opt);
  }

  // ── Total formatting ─────────────────────────────────────────────
  function fmt(amount, currency) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: currency || cfg.currency || "EUR",
      }).format(Number(amount));
    } catch (_) {
      return Number(amount).toFixed(2) + " " + (currency || cfg.currency || "EUR");
    }
  }

  function setTotal(amount, currency) {
    const formatted = fmt(amount, currency);
    currentTotalDisplay = formatted;
    if (totalEl) totalEl.textContent = formatted;
    if (payAmount) payAmount.textContent = formatted;
    if (payOverlayAmount) payOverlayAmount.textContent = formatted;
  }

  setTotal(cfg.rate * (parseInt(nightsSel.value, 10) || 1), cfg.currency);

  // ── Stage track (QR pane) ────────────────────────────────────────
  // Each step maps 1:1 to a real backend state — no timer-driven progress:
  //   scan    → booking PENDING, QR shown, waiting for the user_connect scan
  //   approve → "scanned" event (LoginToken bound, IDENTITY_REQUESTED fired);
  //             user is approving on mobile
  //   fetch   → identity "status" event with status processing/awaiting/
  //             analyzing — the broker is actively resolving the identity
  //   done    → "form_filled" event (IDENTITY_FILLED, fields delivered)
  // Activating one step marks all earlier steps done; later steps stay pending.
  const STAGE_ORDER = ["scan", "approve", "fetch", "done"];

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
    setQrStatus(reason || "Identity request failed.", "error");
  }

  // ── Form auto-fill ───────────────────────────────────────────────
  function fillFieldNow(field, value) {
    const el = inputs[field];
    if (!el) return;
    el.value = value;
    el.classList.remove("field-typing");
    el.classList.add("filled");
  }

  function revealFields(data) {
    if (!data) return;
    const targets = fields.filter(
      (f) => typeof data[f] === "string" && data[f].length && !inputs[f].classList.contains("filled")
    );
    targets.forEach((f, i) => {
      const el = inputs[f];
      el.classList.add("field-typing");
      el.value = "";
      // shimmer for ~360 ms before the value lands, staggered per field
      setTimeout(() => fillFieldNow(f, data[f]), 360 + i * 220);
    });
  }

  function applyFormDataInstant(data) {
    if (!data) return;
    fields.forEach((f) => {
      if (typeof data[f] === "string" && data[f].length) {
        inputs[f].value = data[f];
        inputs[f].classList.add("filled");
      }
    });
  }

  function enablePay(enabled) {
    payBtn.disabled = !enabled;
  }

  function setQrStatus(text, cls) {
    if (!qrStatus) return;
    qrStatus.textContent = text || "";
    qrStatus.className = "sr-only " + (cls || "");
  }

  function setFormStatus(text, cls) {
    if (!formStatus) return;
    formStatus.textContent = text || "";
    formStatus.className = "form-status sr-only " + (cls || "");
  }

  // ── Pay overlay ──────────────────────────────────────────────────
  // Each step maps 1:1 to a real backend state — no timer-driven progress:
  //   request → POST /rest/booking/pay/ accepted (PAYMENT_REQUESTED)
  //   approve → request accepted by broker; user approving on mobile
  //   charge  → "charging" event, emitted by _handle_payment_completion the
  //             instant it calls the bank (call_services) — real bank action
  //   done    → "paid" event (PAID, payment reference returned)
  const PAY_ORDER = ["request", "approve", "charge", "done"];

  function setPayStep(name, status) {
    // status: 'active' | 'done' | 'error'
    const idx = PAY_ORDER.indexOf(name);
    if (idx < 0) return;
    paySteps.forEach((step, i) => {
      step.classList.remove("pending", "active", "done", "error");
      if (status === "error" && i === idx) {
        step.classList.add("error");
      } else if (i < idx) {
        step.classList.add("done");
      } else if (i === idx) {
        step.classList.add(status || "active");
      } else {
        step.classList.add("pending");
      }
    });
  }

  function showPayOverlay() {
    if (!payOverlay) return;
    payOverlay.classList.add("visible");
    payOverlay.setAttribute("aria-hidden", "false");
    setPayStep("request", "active");
    setPayOverlayStatus("Securing your payment session…", "");
    if (payOverlayAmount) payOverlayAmount.textContent = currentTotalDisplay;
  }

  function hidePayOverlay() {
    if (!payOverlay) return;
    payOverlay.classList.remove("visible", "success");
    payOverlay.setAttribute("aria-hidden", "true");
    paySteps.forEach((s) => s.classList.remove("active", "done", "error"));
    paySteps.forEach((s) => s.classList.add("pending"));
  }

  function payOverlaySuccess() {
    if (!payOverlay) return;
    setPayStep("done", "done");
    payOverlay.classList.add("success");
    setPayOverlayStatus("Payment complete. Redirecting…", "ok");
  }

  function setPayOverlayStatus(text, cls) {
    if (!payOverlayStatus) return;
    payOverlayStatus.textContent = text || "";
    payOverlayStatus.className = "pay-overlay-status " + (cls || "");
  }

  // ── QR auto-refresh ──────────────────────────────────────────────
  // Connect token envelope expires after 5 min. Refresh ~30 s before
  // expiry so the visible QR is always scannable. Stops once scanned.
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
    if (phase !== "identity") return;
    try {
      const res = await fetch("/rest/booking/qr/", {
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

  // Initial state from server
  applyFormDataInstant({
    full_name: inputs.full_name.value,
    address: inputs.address.value,
    country: inputs.country.value,
    vat: inputs.vat.value,
  });
  if (cfg.status === "identity_filled" || cfg.status === "payment_requested") {
    enablePay(true);
    setStage("done");
    setQrStatus("Identity verified.", "authenticated");
  } else {
    setStage("scan");
    scheduleQrRefresh();
  }

  // ── Nights change → POST to /rest/booking/nights/ ────────────────
  nightsSel.addEventListener("change", async () => {
    const nights = parseInt(nightsSel.value, 10) || 1;
    setTotal(cfg.rate * nights, cfg.currency);
    try {
      const res = await fetch("/rest/booking/nights/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ nights }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.total) setTotal(data.total, data.currency);
      }
    } catch (_) {
      /* network blip — ignore */
    }
  });

  // ── Pay button ───────────────────────────────────────────────────
  document.getElementById("checkinForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (payBtn.disabled) return;
    payBtn.disabled = true;
    phase = "payment";
    showPayOverlay();
    setFormStatus("Processing payment — approve on PERMYT.", "info");
    try {
      const res = await fetch("/rest/booking/pay/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const reason = err.error || "Payment failed.";
        setPayStep("request", "error");
        setPayOverlayStatus(reason, "error");
        setFormStatus(reason, "error");
        payBtn.disabled = false;
        // give the user a beat to read the error before clearing
        setTimeout(hidePayOverlay, 2400);
        phase = "identity";
      } else {
        // request accepted by broker — advance to approval step
        setPayStep("approve", "active");
        setPayOverlayStatus("Tap approve in your PERMYT app.", "");
      }
    } catch (_) {
      setPayStep("request", "error");
      setPayOverlayStatus("Network error. Please try again.", "error");
      setFormStatus("Network error. Please try again.", "error");
      payBtn.disabled = false;
      setTimeout(hidePayOverlay, 2400);
      phase = "identity";
    }
  });

  // ── WebSocket ────────────────────────────────────────────────────
  function openSocket() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(proto + "//" + window.location.host + "/ws/");
    ws.addEventListener("message", (msg) => {
      let payload;
      try { payload = JSON.parse(msg.data); } catch (_) { return; }
      switch (payload.event) {
        case "scanned":
          // Real backend state: LoginToken bound, identity request fired.
          if (phase === "identity") {
            stopQrRefresh();
            setStage("approve");
            setQrStatus("Scanned — approve on PERMYT.", "info");
            setFormStatus("PERMYT is asking for your details. Approve on mobile.", "info");
          }
          break;
        case "status":
          // Intermediate broker status for a request. For the identity leg,
          // statuses processing/awaiting/analyzing mean the broker is actively
          // resolving the user's details — advance the real "fetch" step.
          // Terminal statuses (completed/failed) are handled by their own
          // events (form_filled / identity_failed / paid / *_failed).
          if (
            phase === "identity" &&
            payload.kind === "identity" &&
            ["processing", "awaiting", "analyzing"].indexOf(payload.status) !== -1
          ) {
            // only move forward, never regress past 'fetch'
            const onApprove = stageSteps.some(
              (s) => s.classList.contains("active") && s.dataset.stage === "approve"
            );
            if (onApprove) {
              setStage("fetch");
              setQrStatus("Retrieving your verified details…", "info");
            }
          }
          break;
        case "form_filled":
          phase = "identity";
          setStage("done");
          revealFields(payload.form_data || {});
          enablePay(true);
          if (payload.total && payload.currency) setTotal(payload.total, payload.currency);
          setQrStatus("Identity verified.", "authenticated");
          setFormStatus("Identity verified. Ready to pay.", "ok");
          break;
        case "identity_failed":
          phase = "identity";
          setStageError("fetch", payload.reason);
          setFormStatus(payload.reason || "Identity request failed.", "error");
          break;
        case "charging":
          // Real backend state: _handle_payment_completion is calling the
          // bank right now. Activate the "charge" step — this is no longer
          // visual fakery, it reflects an actual provider call.
          if (phase === "payment") {
            setPayStep("charge", "active");
            setPayOverlayStatus("Your bank is settling the payment…", "");
          }
          break;
        case "paid":
          payOverlaySuccess();
          setFormStatus("Payment complete. Redirecting…", "ok");
          enablePay(false);
          setTimeout(() => { window.location.href = "/confirmation/"; }, 900);
          break;
        case "payment_failed":
          setPayStep("charge", "error");
          setPayOverlayStatus(payload.reason || "Payment failed.", "error");
          setFormStatus(payload.reason || "Payment failed.", "error");
          enablePay(true);
          phase = "identity";
          setTimeout(hidePayOverlay, 2400);
          break;
        default:
          break;
      }
    });
    ws.addEventListener("close", () => setTimeout(openSocket, 1500));
  }
  openSocket();
})();
