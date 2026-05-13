const messagesEl = document.querySelector("#messages");
const formEl = document.querySelector("#chatForm");
const inputEl = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const newSessionButton = document.querySelector("#newSessionButton");
const reportBoard = document.querySelector("#reportBoard");
const reportBadge = document.querySelector("#reportBadge");
const patientStatus = document.querySelector("#patientStatus");
const locationStatus = document.querySelector("#locationStatus");
const modeStatus = document.querySelector("#modeStatus");
const traceToggle = document.querySelector("#traceToggle");
const traceDialog = document.querySelector("#traceDialog");
const traceClose = document.querySelector("#traceClose");
const traceList = document.querySelector("#traceList");

let sessionId = localStorage.getItem("med_session_id");
let latestTrace = [];

const pipelineAliases = {
  question_classifier: "question_classifier",
  followup_responder: "question_classifier",
  domain_expert: "domain_expert",
  intake: "intake",
  location: "location",
  triage: "triage",
  emergency: "triage",
  diagnosis: "diagnosis",
  verifier: "diagnosis",
  panel: "panel",
  primary_diagnostician: "panel",
  skeptical_reviewer: "panel",
  evidence_auditor: "panel",
  safety_triage_lead: "panel",
  conflict_detector: "panel",
  adjudicator: "panel",
  hospital: "hospital",
  hospital_finder: "hospital",
  risk: "risk",
  risk_analyzer: "risk",
  tests: "tests",
  test_recommender: "tests",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function addMessage(role, content, meta = "") {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="message-meta">${escapeHtml(meta || (role === "user" ? "You" : "Assistant"))}</div>
    <div class="message-bubble">${escapeHtml(content)}</div>
  `;
  messagesEl.appendChild(article);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setBusy(isBusy) {
  inputEl.disabled = isBusy;
  sendButton.disabled = isBusy;
  if (isBusy) {
    modeStatus.textContent = "Agents running";
  }
}

function updateSessionStatus(memory = {}) {
  const name = memory.name || "Not set";
  const age = memory.age ? `, ${memory.age}` : "";
  patientStatus.textContent = `${name}${age}`;

  const location = memory.location || memory.location_candidate || {};
  locationStatus.textContent = location.formatted || location.text || (memory.awaiting_location ? "Needed" : "Pending");

  if (memory.awaiting_hospital_selection) {
    modeStatus.textContent = "Hospital lookup";
  } else if (memory.confirm_location) {
    modeStatus.textContent = "Confirm location";
  } else if (memory.awaiting_name || memory.awaiting_age || memory.awaiting_location) {
    modeStatus.textContent = "Intake";
  } else {
    modeStatus.textContent = "Consultation";
  }
}

function updatePipeline(trace = []) {
  latestTrace = trace;
  const active = new Set(
    trace
      .map((item) => pipelineAliases[item.agent || item.name || item.node])
      .filter(Boolean)
  );
  document.querySelectorAll("#pipelineList li").forEach((li) => {
    li.classList.toggle("active", active.has(li.dataset.agent));
  });
}

function confidencePercent(value) {
  const parsed = Number(value || 0);
  return Math.max(0, Math.min(100, Math.round(parsed * 100)));
}

function renderDiagnoses(diagnoses = []) {
  if (!diagnoses.length) return "";
  return `
    <section>
      <div class="section-title">Diagnosis <span class="tag">Top ${escapeHtml(diagnoses[0].disease || "Unknown")}</span></div>
      <div class="metric-grid">
        ${diagnoses.slice(0, 3).map((diag) => {
          const pct = confidencePercent(diag.confidence);
          return `
            <div class="metric-card">
              <strong>${escapeHtml(diag.disease || "Unknown")}</strong>
              <p class="small-muted">${escapeHtml(diag.reason || "No rationale returned.")}</p>
              <div class="confidence">
                <div class="confidence-track"><div class="confidence-fill" style="width:${pct}%"></div></div>
                <span>${pct}%</span>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderListSection(title, items = [], variant = "") {
  if (!items.length) return "";
  return `
    <section>
      <div class="section-title">${escapeHtml(title)}</div>
      <div class="tag-list">
        ${items.map((item) => `<span class="tag ${variant}">${escapeHtml(typeof item === "string" ? item : item.test_name || item.reason || JSON.stringify(item))}</span>`).join("")}
      </div>
    </section>
  `;
}

function renderPanel(panel = {}) {
  if (!Object.keys(panel).length) return "";
  const conflicts = Number(panel.conflict_count || 0);
  return `
    <section class="panel-card">
      <div class="section-title">
        Medical panel
        <span class="tag ${conflicts ? "amber" : ""}">${conflicts ? `${conflicts} conflict(s)` : "Consensus"}</span>
      </div>
      <p class="small-muted">${escapeHtml(panel.panel_summary || "Panel review completed.")}</p>
      ${panel.why_final_won ? `<p class="small-muted"><strong>Decision:</strong> ${escapeHtml(panel.why_final_won)}</p>` : ""}
      ${panel.resolving_test ? `<p class="small-muted"><strong>Resolving test:</strong> ${escapeHtml(panel.resolving_test)}</p>` : ""}
    </section>
  `;
}

function renderHospitals(hospitals = []) {
  if (!hospitals.length) return "";
  return `
    <section>
      <div class="section-title">Nearby hospitals <span class="tag">Select for doctors</span></div>
      <div class="hospital-grid">
        ${hospitals.slice(0, 5).map((hospital, index) => {
          const distance = typeof hospital.distance_m === "number" ? `${(hospital.distance_m / 1000).toFixed(1)} km` : "";
          const travel = typeof hospital.travel_time_s === "number" ? `${Math.round(hospital.travel_time_s / 60)} min` : "";
          return `
            <div class="hospital-card">
              <strong>${index + 1}. ${escapeHtml(hospital.name || "Hospital")}</strong>
              <p class="small-muted">${escapeHtml([distance, travel].filter(Boolean).join(" • "))}</p>
              ${hospital.address ? `<p class="small-muted">${escapeHtml(hospital.address)}</p>` : ""}
              ${hospital.aligned ? `<span class="tag">Diagnosis match</span>` : ""}
              <button type="button" data-hospital-choice="${index + 1}">Find doctors</button>
            </div>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderDoctors(details = {}) {
  const doctors = details.doctors || [];
  return `
    <section>
      <div class="section-title">Hospital details</div>
      <div class="hospital-card">
        <strong>${escapeHtml(details.hospital_name || "Selected hospital")}</strong>
        ${details.address ? `<p class="small-muted">${escapeHtml(details.address)}</p>` : ""}
        ${(details.phone_numbers || []).map((phone) => `<span class="tag">${escapeHtml(phone)}</span>`).join("")}
        ${details.website ? `<p class="small-muted">${escapeHtml(details.website)}</p>` : ""}
        ${doctors.length ? `
          <div class="tag-list">
            ${doctors.map((doctor) => `<span class="tag">${escapeHtml(doctor.name || "Doctor")}</span>`).join("")}
          </div>
        ` : `<p class="small-muted">No specific doctor profiles found online. Contact the hospital directly for availability.</p>`}
      </div>
    </section>
  `;
}

function renderReport(payload = {}) {
  const data = payload.structured || {};
  const raw = payload.raw || {};
  const diagnosis = raw.diagnosis || {};
  const diagnoses = diagnosis.diagnoses || [];
  const risks = Array.isArray(data.risks) ? data.risks : (raw.risks?.risks || raw.risks || []);
  const tests = Array.isArray(data.recommended_tests) ? data.recommended_tests : (raw.tests?.tests || raw.tests || []);
  const hospitals = data.hospitals || raw.hospitals || [];
  const remedy = data.immediate_actions || raw.remedy?.remedy_steps || [];

  reportBoard.classList.remove("empty-state");
  reportBadge.textContent = data.emergency || raw.is_emergency ? "Emergency" : "Updated";
  reportBadge.classList.toggle("emergency", Boolean(data.emergency || raw.is_emergency));

  if (payload.kind === "followup") {
    reportBoard.innerHTML = `
      <section class="followup-card">
        <div class="section-title">Follow-up answer</div>
        <p class="small-muted">${escapeHtml(raw.followup_answer || payload.message)}</p>
      </section>
    `;
    return;
  }

  if (payload.kind === "hospital_details") {
    reportBoard.insertAdjacentHTML("afterbegin", renderDoctors(payload.details || {}));
    return;
  }

  reportBoard.innerHTML = [
    renderDiagnoses(diagnoses),
    renderListSection("Immediate actions", remedy, "warn"),
    renderPanel(data.panel_decision || raw.panel_decision || {}),
    renderListSection("Risk flags", risks, "warn"),
    renderListSection("Recommended tests", tests),
    renderHospitals(hospitals),
  ].filter(Boolean).join("") || `<p class="small-muted">No structured report returned yet.</p>`;
}

async function createSession() {
  const response = await fetch("/api/session", { method: "POST" });
  if (!response.ok) throw new Error("Could not start session");
  const data = await response.json();
  sessionId = data.session_id;
  localStorage.setItem("med_session_id", sessionId);
  updateSessionStatus(data.session_memory || {});
  return sessionId;
}

async function ensureSession() {
  if (!sessionId) return createSession();

  const response = await fetch(`/api/session/${encodeURIComponent(sessionId)}`);
  if (response.ok) {
    const data = await response.json();
    updateSessionStatus(data.session_memory || {});
    return sessionId;
  }

  if (response.status === 404) {
    localStorage.removeItem("med_session_id");
    sessionId = null;
    return createSession();
  }

  throw new Error("Could not restore session");
}

async function sendMessage(message, meta = "Assistant") {
  await ensureSession();
  setBusy(true);
  const pending = document.createElement("article");
  pending.className = "message assistant";
  pending.innerHTML = `<div class="message-meta">${escapeHtml(meta)}</div><div class="message-bubble"><span class="loading">Agents are thinking through the case</span></div>`;
  messagesEl.appendChild(pending);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    let response = await fetch(`/api/session/${encodeURIComponent(sessionId)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (response.status === 404) {
      localStorage.removeItem("med_session_id");
      sessionId = null;
      await ensureSession();
      response = await fetch(`/api/session/${encodeURIComponent(sessionId)}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Request failed");
    }
    const data = await response.json();
    pending.remove();
    addMessage("assistant", data.message || "Done.", data.kind === "hospital_details" ? "Hospital details" : "Assistant");
    updateSessionStatus(data.session_memory || {});
    updatePipeline(data.agent_trace || []);
    if (data.structured || data.raw || data.details) {
      renderReport(data);
    }
  } catch (error) {
    pending.remove();
    addMessage("assistant", `I could not complete that request: ${error.message}`, "Error");
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  inputEl.style.height = "auto";
  addMessage("user", message);
  await sendMessage(message);
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 150)}px`;
});

reportBoard.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-hospital-choice]");
  if (!button) return;
  const choice = button.dataset.hospitalChoice;
  addMessage("user", choice, "Hospital selection");
  await sendMessage(choice, "Hospital finder");
});

newSessionButton.addEventListener("click", async () => {
  localStorage.removeItem("med_session_id");
  sessionId = null;
  latestTrace = [];
  messagesEl.innerHTML = "";
  updatePipeline([]);
  reportBadge.textContent = "Waiting";
  reportBadge.classList.remove("emergency");
  reportBoard.className = "report-board empty-state";
  reportBoard.innerHTML = `<div class="empty-pulse"></div><p>Your diagnosis, panel summary, risk flags, tests, and hospitals will appear here after the agents run.</p>`;
  await start();
});

traceToggle.addEventListener("click", () => {
  traceList.innerHTML = latestTrace.length
    ? latestTrace.map((item) => `
      <div class="trace-item">
        <code>${escapeHtml(item.agent || item.name || item.node || "agent")}</code>
        <p class="small-muted">${escapeHtml(item.ok === false ? "Failed" : "Completed")} ${item.duration_s ? `in ${Number(item.duration_s).toFixed(2)}s` : ""}</p>
      </div>
    `).join("")
    : `<p class="small-muted">No trace for this session yet.</p>`;
  traceDialog.showModal();
});

traceClose.addEventListener("click", () => traceDialog.close());

async function start() {
  await ensureSession();
  addMessage("assistant", "Welcome to MedOrchestrator. Please share your name to begin.", "Assistant");
}

start().catch((error) => {
  addMessage("assistant", `Startup failed: ${error.message}`, "Error");
});
