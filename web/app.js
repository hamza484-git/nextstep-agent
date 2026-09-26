/* NextStep Agent Ops Console — client */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const API = "";  // same origin (served by FastAPI)

  const el = {
    input: $("#input"), btnRun: $("#btn-run"), status: $("#run-status"),
    pillProvider: $("#pill-provider"), statusDot: $("#status-dot"),
    safety: {
      at_risk:   $('.safety-item[data-key="at_risk"]'),
      injection: $('.safety-item[data-key="injection"]'),
      harmful:   $('.safety-item[data-key="harmful"]'),
      off_topic: $('.safety-item[data-key="off_topic"]'),
    },
    asmtMeta: $("#asmt-meta"), asmtBody: $("#asmt-body"),
    actionsList: $("#actions-list"),
    ledgerBody: $("#ledger-body"),
    trace: $("#trace"),
  };

  let currentSid = null;

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  async function init() {
    try {
      const h = await fetch(API + "/health").then(r => r.json());
      el.pillProvider.textContent = `provider: ${h.provider} · ${h.model}`;
      el.statusDot.dataset.state = "on";
    } catch { el.statusDot.dataset.state = "off"; el.pillProvider.textContent = "provider: offline"; }

    $$(".chip").forEach(b => b.addEventListener("click", () => {
      el.input.value = PRESETS[b.dataset.preset] || "";
      el.input.focus();
    }));
    el.btnRun.addEventListener("click", run);
    el.input.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run();
    });

    refreshLedger();
  }

  async function run() {
    const text = (el.input.value || "").trim();
    if (!text) return;
    el.btnRun.disabled = true;
    el.status.textContent = "▸ running agent loop…";
    resetPanels();

    try {
      const t0 = performance.now();
      const resp = await fetch(API + "/v1/situations", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": "console-" + Date.now() },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();
      const dt = Math.round(performance.now() - t0);
      if (data.assessment === null && data.stopped_reason) {
        el.status.textContent = `▸ stopped: ${data.stopped_reason} · ${dt}ms`;
      } else {
        el.status.textContent = `▸ done · ${dt}ms · ${(data.trace||[]).length} steps`;
      }
      currentSid = data.situation_id;
      renderAll(data);
      refreshLedger();
    } catch (e) {
      el.status.textContent = "▸ error: " + e.message;
    } finally { el.btnRun.disabled = false; }
  }

  function resetPanels() {
    for (const k of Object.keys(el.safety)) el.safety[k].removeAttribute("data-fired");
    el.asmtBody.innerHTML = `<p class="placeholder">— running… —</p>`;
    el.asmtMeta.textContent = "";
    el.actionsList.innerHTML = `<p class="placeholder">— waiting for agent —</p>`;
    el.trace.innerHTML = `<li class="placeholder">— streaming… —</li>`;
  }

  function renderAll(data) {
    renderSafety(data);
    renderAssessment(data.assessment);
    renderActions(data);
    renderTrace(data.trace || []);
  }

  function renderSafety(data) {
    // The agent's safety flags live inside the assessment.risk_flags,
    // plus the safety pre-pass emits a trace step with the flags list.
    // We derive our light indicators from what's actually present.
    const a = data.assessment;
    const flags = (a && a.risk_flags) || [];
    const off = data.stopped_reason;
    const mapping = {
      at_risk:   flags.includes("at_risk_emotional"),
      injection: flags.includes("prompt_injection"),
      harmful:   flags.includes("harmful_request") || off === "harmful",
      off_topic: flags.includes("off_topic"),
    };
    for (const [k, fired] of Object.entries(mapping)) {
      el.safety[k].dataset.fired = String(fired);
    }
  }

  function renderAssessment(a) {
    if (!a) {
      el.asmtBody.innerHTML = `<p class="placeholder">— agent produced no assessment (safety block or LLM failure) —</p>`;
      return;
    }
    el.asmtMeta.textContent = `v${a.version} · uncertainty ${a.uncertainty.toFixed(2)}`;
    const flags = a.risk_flags || [];
    const modeText = a.calm_mode ? "CALM MODE" : a.recovery_mode ? "RECOVERY MODE" : null;
    let html = `<div class="asmt-summary">${escapeHtml(a.summary)}</div>`;
    html += `<div class="asmt-badges">
      <span class="badge" data-level="${a.urgency}">urgency: ${a.urgency}</span>
      ${modeText ? `<span class="badge badge-mode">${modeText}</span>` : ""}
      ${flags.map(f => `<span class="badge badge-flag">${escapeHtml(f)}</span>`).join("")}
    </div>`;
    if (a.priorities && a.priorities.length) {
      for (const p of a.priorities) {
        html += `<div class="priority-item">
          <div class="prio-num">#${p.rank}</div>
          <div>
            <h4>${escapeHtml(p.title)}</h4>
            <p class="why">${escapeHtml(p.why)}</p>
            ${p.action ? `<p class="action">${escapeHtml(p.action)}</p>` : `<p class="action" style="opacity:.6">needs clarification</p>`}
          </div>
        </div>`;
      }
    } else if (!modeText) {
      html += `<p class="placeholder">— no priorities produced —</p>`;
    }
    if (a.notes_to_user) {
      html += `<div class="asmt-summary" style="border-left-color: var(--violet); font-size: 12px; color: var(--text-soft)">${escapeHtml(a.notes_to_user)}</div>`;
    }
    el.asmtBody.innerHTML = html;
  }

  function renderActions(data) {
    const planned = data.planned || [];
    const executed = (data.executed || []).reduce((acc, e) => { acc[e.action_id] = e; return acc; }, {});
    if (planned.length === 0) {
      el.actionsList.innerHTML = `<p class="placeholder">— no actions planned (safety block, calm mode, or recovery mode) —</p>`;
      return;
    }
    el.actionsList.innerHTML = "";
    for (const p of planned) {
      const tier = String(p.reversibility || "silent").toLowerCase();
      const isConfirm = tier === "confirm";
      const isBlock = tier === "block";
      const exec = executed[p.action_id];
      const card = document.createElement("div");
      card.className = "action-card";
      card.dataset.tier = tier;
      card.dataset.executed = String(!!exec);
      card.innerHTML = `
        <div class="action-head">
          <span class="action-tool">${escapeHtml(p.tool)}(...)</span>
          <span class="action-tier-badge">${tier}</span>
        </div>
        <div class="action-body">
          <p class="rationale">${escapeHtml(p.rationale || "")}</p>
          <span class="blast"><strong>blast_radius:</strong> ${escapeHtml(p.blast_radius || "")}</span>
          ${p.preview ? `<div class="action-preview">${escapeHtml(p.preview)}</div>` : ""}
        </div>
        ${exec
          ? `<div class="action-executed-note">✓ EXECUTED · attempt ${escapeHtml(exec.attempt_id || "?").slice(0,12)}… · ok=${exec.ok}</div>`
          : isConfirm
          ? `<div class="action-confirm">
              <button class="btn btn-reject" data-reject="${p.action_id}">Reject</button>
              <button class="btn btn-approve" data-approve="${p.action_id}">Approve &amp; execute</button>
            </div>`
          : isBlock
          ? `<div class="action-executed-note" style="color: var(--red); background: var(--red-soft)">✗ BLOCKED</div>`
          : ""}`;
      el.actionsList.appendChild(card);
    }
    // wire approve buttons
    el.actionsList.querySelectorAll("[data-approve]").forEach(b => b.addEventListener("click", () => confirmAction(b.dataset.approve)));
    el.actionsList.querySelectorAll("[data-reject]").forEach(b => b.addEventListener("click", () => rejectAction(b.dataset.reject)));
  }

  async function confirmAction(aid) {
    if (!currentSid) return;
    try {
      const resp = await fetch(API + `/v1/situations/${currentSid}/confirm/${aid}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_context: { situation_id: currentSid } }),
      });
      const data = await resp.json();
      if (!resp.ok) { alert("Confirm failed: " + (data.detail || resp.status)); return; }
      renderAll(data.run);
      refreshLedger();
    } catch (e) { alert("Confirm error: " + e.message); }
  }

  function rejectAction(aid) {
    // find the card and grey it out; nothing sent to server
    const card = el.actionsList.querySelector(`[data-approve="${aid}"]`)?.closest(".action-card");
    if (card) {
      card.dataset.executed = "true";
      const c = card.querySelector(".action-confirm");
      if (c) c.outerHTML = `<div class="action-executed-note" style="color: var(--text-mute)">— user rejected —</div>`;
    }
  }

  function renderTrace(trace) {
    if (!trace.length) { el.trace.innerHTML = `<li class="placeholder">— no trace —</li>`; return; }
    el.trace.innerHTML = "";
    for (const t of trace) {
      const li = document.createElement("li");
      li.dataset.kind = t.kind;
      li.innerHTML = `
        <span class="step-kind">${t.kind}</span>
        <span class="step-note">${escapeHtml(t.note || "")}</span>
        ${t.tool ? `<span class="step-tool">${escapeHtml(t.tool)}(${escapeHtml(JSON.stringify(t.args || {}))})</span>` : ""}`;
      el.trace.appendChild(li);
    }
    el.trace.scrollTop = el.trace.scrollHeight;
  }

  async function refreshLedger() {
    try {
      const r = await fetch(API + "/v1/ledger?limit=20").then(x => x.json());
      const rows = r.rows || [];
      if (!rows.length) { el.ledgerBody.innerHTML = `<p class="placeholder">— empty —</p>`; return; }
      el.ledgerBody.innerHTML = "";
      // newest first
      for (const row of rows.slice().reverse()) {
        const d = document.createElement("div");
        d.className = "ledger-row";
        const at = row.at ? new Date(row.at).toLocaleTimeString() : "";
        d.innerHTML = `
          <span class="ledger-kind" data-kind="${row.kind}">${row.kind}</span>
          <span class="ledger-id">${(row.action_id || row.tool || "").slice(0, 20)}</span>
          <span class="ledger-time">${at}</span>`;
        el.ledgerBody.appendChild(d);
      }
    } catch { /* ignore */ }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
