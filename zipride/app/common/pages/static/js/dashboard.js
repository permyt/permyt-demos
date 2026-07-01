/* Zipride driver-verification dashboard: live stage track + source-direct
   answer reveal, driven by Log rows the broker callback upserts as the request
   advances. */

(function () {
  "use strict";

  function getCookie(name) {
    const v = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return v ? v.pop() : "";
  }
  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  const collectedEl = document.getElementById("collected");
  const collectedEmptyEl = document.getElementById("collectedEmpty");
  const collectedDoneEl = document.getElementById("collectedDone");
  const stageSteps = Array.from(document.querySelectorAll("#stageTrack .stage-step"));

  let currentRequestId = null;
  const shownFacts = new Set();

  // ── Stage track ──────────────────────────────────────────────────
  const STAGE_ORDER = ["sent", "approval", "approved", "answers"];
  const STATUS_TO_STAGE = {
    submitted: "sent", queued: "sent", analyzing: "sent",
    awaiting: "approval",
    processing: "approved", fetching: "approved",
    answers: "answers", done: "answers",
  };

  function setStage(name, failed) {
    const idx = STAGE_ORDER.indexOf(name);
    if (idx < 0) return;
    stageSteps.forEach((step) => {
      const i = STAGE_ORDER.indexOf(step.dataset.stage);
      step.classList.remove("pending", "active", "done", "error");
      if (failed && i === idx) step.classList.add("error");
      else if (i < idx) step.classList.add("done");
      else if (i === idx) step.classList.add(name === "answers" ? "done" : "active");
      else step.classList.add("pending");
    });
  }

  // ── Source-direct answer reveal ──────────────────────────────────
  function revealCollected(facts) {
    if (!Array.isArray(facts) || facts.length === 0) return;
    if (collectedEmptyEl) collectedEmptyEl.classList.add("hidden");
    facts.forEach((f, i) => {
      const key = f.label + "::" + f.value;
      if (shownFacts.has(key)) return;
      shownFacts.add(key);
      const src = f.source || "";
      const row = document.createElement("div");
      row.className = "fact-card field-typing";
      row.innerHTML =
        '<div class="fact-head"><span class="fact-label">' + escapeHtml(f.label) + "</span>" +
        '<span class="fact-source" data-src="' + escapeHtml(src) + '">' + escapeHtml(src) + "</span></div>" +
        '<div class="fact-value">' + escapeHtml(f.value) + "</div>";
      collectedEl.appendChild(row);
      setTimeout(() => {
        row.classList.remove("field-typing");
        row.classList.add("filled");
      }, 200 + i * 160);
    });
    if (collectedDoneEl) collectedDoneEl.classList.remove("hidden");
  }

  // ── Apply one Log row (used for both the initial state and live WS) ──
  const liveEl = document.querySelector(".onboard-live");
  const retryBtn = document.getElementById("retryBtn");

  function setLive(text, failed) {
    if (!liveEl) return;
    if (text === null) { liveEl.style.display = "none"; return; }
    liveEl.style.display = "";
    liveEl.classList.toggle("is-error", !!failed);
    liveEl.innerHTML = failed
      ? '<i data-lucide="alert-triangle"></i> ' + text
      : '<span class="spinner"></span> ' + text;
    if (window.lucide) lucide.createIcons();
  }

  function applyRow(fields) {
    if (!fields) return;
    const reqId = fields.permyt_request_id;
    if (!reqId || (currentRequestId && reqId !== currentRequestId)) return;
    currentRequestId = reqId;
    const d = fields.data || {};
    const failed = fields.success === false;
    const stage = d.stage || STATUS_TO_STAGE[d.status] || null;
    if (stage) setStage(stage, failed);
    if (d.collected) revealCollected(d.collected);
    if (failed) {
      setLive("We couldn't complete your check — " + (d.reason || d.error || d.note || "please try again."), true);
      if (retryBtn) retryBtn.hidden = false;
    } else if (stage === "answers") {
      setLive(null);
      if (retryBtn) retryBtn.hidden = true;
    }
  }

  // ── Retry: re-fire the verification request after a failure ────────
  function resetForRetry() {
    currentRequestId = null;
    shownFacts.clear();
    if (collectedEl) collectedEl.innerHTML = "";
    if (collectedEmptyEl) collectedEmptyEl.classList.remove("hidden");
    if (collectedDoneEl) collectedDoneEl.classList.add("hidden");
    stageSteps.forEach(function (s) {
      s.classList.remove("active", "done", "error");
      s.classList.add("pending");
    });
    if (retryBtn) retryBtn.hidden = true;
    setLive("Checking with the authoritative sources…", false);
  }

  if (retryBtn) {
    retryBtn.addEventListener("click", async function () {
      retryBtn.disabled = true;
      resetForRetry();
      try {
        const resp = await fetch("/rest/requests/submit/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
          body: JSON.stringify({}),
        });
        const data = await resp.json();
        if (resp.ok && data.request_id) {
          currentRequestId = data.request_id;
          setStage("sent");
        }
      } catch (_) { /* WS / state poll will still reflect progress */ }
      retryBtn.disabled = false;
    });
  }

  // Verification auto-starts on connect; reflect whatever state already exists
  // (covers a reload mid-flow or after completion), then live WS takes over.
  fetch("/rest/onboarding/state/", { headers: { Accept: "application/json" } })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (d && d.request_id) {
        applyRow({ permyt_request_id: d.request_id, data: d.data, success: d.success });
      }
    })
    .catch(function () { /* ignore — WS still delivers live updates */ });

  // ── WebSocket ────────────────────────────────────────────────────
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(protocol + "//" + window.location.host + "/ws/");
  let pingInterval;
  ws.addEventListener("open", function () {
    pingInterval = setInterval(function () {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 30000);
  });
  ws.addEventListener("close", function () { clearInterval(pingInterval); });

  ws.addEventListener("message", function (e) {
    let msg;
    try { msg = JSON.parse(e.data); } catch (_) { return; }
    if (msg.model !== "Log") return;
    const rows = Array.isArray(msg.data) ? msg.data : [msg.data];
    for (const row of rows) {
      if (!row) continue;
      applyRow(row.fields || row);
    }
  });
})();
