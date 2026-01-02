const API_BASE = "";

const SUMMARY_VARIANT_ORDER = [
  "summary_text",
  "summary_player",
  "summary_dm",
  "summary_hooks",
  "summary_npc_changes",
];

const SUMMARY_VARIANT_LABELS = {
  summary_text: "Main Summary",
  summary_player: "Player Recap",
  summary_dm: "DM Prep",
  summary_hooks: "Next Session Hooks",
  summary_npc_changes: "NPC Changes",
};

const state = {
  campaigns: [],
  sessions: [],
  sessionMap: {},
  selectedCampaign: null,
  selectedSession: null,
  selectedRun: null,
  currentUserId: null,
  userRole: "dm",
  authEnabled: false,
  bundle: null,
  questThreads: [],
  campaignEntities: [],
  transcriptLines: [],
  utteranceTimecodes: {},
  runStatusTimer: null,
  summaryVariant: "summary_text",
  summaryFormat: "docx",
};

const elements = {
  campaignSelect: document.getElementById("campaignSelect"),
  userIdInput: document.getElementById("userIdInput"),
  userSetButton: document.getElementById("userSetButton"),
  userRole: document.getElementById("userRole"),
  sessionList: document.getElementById("sessionList"),
  sessionCount: document.getElementById("sessionCount"),
  newSessionSlug: document.getElementById("newSessionSlug"),
  newSessionTitle: document.getElementById("newSessionTitle"),
  newSessionDate: document.getElementById("newSessionDate"),
  newSessionNumber: document.getElementById("newSessionNumber"),
  newSessionFile: document.getElementById("newSessionFile"),
  createSessionButton: document.getElementById("createSessionButton"),
  statusLine: document.getElementById("statusLine"),
  sessionMeta: document.getElementById("sessionMeta"),
  runSelect: document.getElementById("runSelect"),
  summaryVariant: document.getElementById("summaryVariant"),
  summaryFormat: document.getElementById("summaryFormat"),
  startRunButton: document.getElementById("startRunButton"),
  downloadSummary: document.getElementById("downloadSummary"),
  exportSession: document.getElementById("exportSession"),
  deleteSession: document.getElementById("deleteSession"),
  runMetrics: document.getElementById("runMetrics"),
  runProgress: document.getElementById("runProgress"),
  summaryText: document.getElementById("summaryText"),
  qualityMetrics: document.getElementById("qualityMetrics"),
  runDiagnostics: document.getElementById("runDiagnostics"),
  artifactLinks: document.getElementById("artifactLinks"),
  askInput: document.getElementById("askInput"),
  askButton: document.getElementById("askButton"),
  askAnswer: document.getElementById("askAnswer"),
  askCitations: document.getElementById("askCitations"),
  threadList: document.getElementById("threadList"),
  sceneList: document.getElementById("sceneList"),
  eventList: document.getElementById("eventList"),
  quoteList: document.getElementById("quoteList"),
  sessionNote: document.getElementById("sessionNote"),
  saveSessionNote: document.getElementById("saveSessionNote"),
  noteList: document.getElementById("noteList"),
  bookmarkList: document.getElementById("bookmarkList"),
  transcriptText: document.getElementById("transcriptText"),
  entityList: document.getElementById("entityList"),
  entityFilter: document.getElementById("entityFilter"),
  timelineList: document.getElementById("timelineList"),
  questList: document.getElementById("questList"),
  questFilter: document.getElementById("questFilter"),
  codexList: document.getElementById("codexList"),
  codexFilter: document.getElementById("codexFilter"),
  codexSearch: document.getElementById("codexSearch"),
  searchInput: document.getElementById("searchInput"),
  searchButton: document.getElementById("searchButton"),
  semanticToggle: document.getElementById("semanticToggle"),
  sessionOnlyToggle: document.getElementById("sessionOnlyToggle"),
  searchPanel: document.getElementById("searchPanel"),
  searchResults: document.getElementById("searchResults"),
  searchTitle: document.getElementById("searchTitle"),
  searchSub: document.getElementById("searchSub"),
  closeSearch: document.getElementById("closeSearch"),
  entityPanel: document.getElementById("entityPanel"),
  entityTitle: document.getElementById("entityTitle"),
  entityMeta: document.getElementById("entityMeta"),
  entityDetails: document.getElementById("entityDetails"),
  closeEntity: document.getElementById("closeEntity"),
  threadPanel: document.getElementById("threadPanel"),
  threadTitle: document.getElementById("threadTitle"),
  threadMeta: document.getElementById("threadMeta"),
  threadDetails: document.getElementById("threadDetails"),
  closeThread: document.getElementById("closeThread"),
  evidencePanel: document.getElementById("evidencePanel"),
  evidenceTitle: document.getElementById("evidenceTitle"),
  evidenceMeta: document.getElementById("evidenceMeta"),
  evidenceDetails: document.getElementById("evidenceDetails"),
  closeEvidence: document.getElementById("closeEvidence"),
};

function setStatus(message) {
  elements.statusLine.textContent = message;
}

function formatTime(ms) {
  if (ms == null) return "";
  const total = Math.floor(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatTimecode(ms) {
  if (ms == null) return "";
  const total = Math.floor(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return `${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function timecodeForUtterance(utteranceId, startMs) {
  if (utteranceId && state.utteranceTimecodes[utteranceId]) {
    return state.utteranceTimecodes[utteranceId];
  }
  return formatTimecode(startMs);
}

async function fetchJson(path) {
  const headers = {};
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function postJson(path, payload) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function putJson(path, payload) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function uploadTranscript(campaignSlug, sessionSlug, file) {
  const headers = {};
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(
    `${API_BASE}/campaigns/${campaignSlug}/sessions/${sessionSlug}/transcript`,
    {
      method: "POST",
      headers,
      body: form,
    }
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Upload failed: ${response.status}`);
  }
  return response.json();
}

async function askCampaign(question) {
  const headers = { "Content-Type": "application/json" };
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const params = new URLSearchParams();
  if (elements.sessionOnlyToggle?.checked && state.selectedSession) {
    params.set("session_id", state.selectedSession);
  } else if (elements.sessionOnlyToggle && !elements.sessionOnlyToggle.checked) {
    params.set("include_all_runs", "true");
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `${API_BASE}/campaigns/${state.selectedCampaign}/ask${query}`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ question }),
    }
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Ask failed: ${response.status}`);
  }
  return response.json();
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function summaryVariantLabel(variant) {
  return SUMMARY_VARIANT_LABELS[variant] || variant.replace(/_/g, " ");
}

function summaryVariantSlug(variant) {
  if (variant === "summary_text") {
    return "summary";
  }
  return variant.replace(/^summary_/, "");
}

function summaryTextForVariant(bundle, variant) {
  if (!bundle) return "";
  if (bundle.summary_variants && bundle.summary_variants[variant]) {
    return bundle.summary_variants[variant];
  }
  if (variant === "summary_text") {
    return bundle.summary || "";
  }
  return "";
}

function availableSummaryVariants(bundle) {
  if (!bundle) return [];
  const variants = bundle.summary_variants ? Object.keys(bundle.summary_variants) : [];
  if (variants.length > 0) {
    return SUMMARY_VARIANT_ORDER.filter((variant) => variants.includes(variant));
  }
  if (bundle.summary || (bundle.run_status && bundle.run_status !== "completed")) {
    return ["summary_text"];
  }
  return [];
}

function artifactLabel(kind) {
  const match = kind.match(/^(summary(?:_[a-z_]+)?)[_](docx|txt)$/);
  if (match) {
    const prefix = match[1];
    const format = match[2].toUpperCase();
    const variant =
      prefix === "summary" ? "summary_text" : prefix.replace(/^summary_/, "summary_");
    return `${summaryVariantLabel(variant)} (${format})`;
  }
  return kind.replace(/_/g, " ");
}

function renderParagraphs(text, runStatus) {
  clearNode(elements.summaryText);
  if (!text) {
    if (runStatus && runStatus !== "completed") {
      if (runStatus === "failed") {
        elements.summaryText.textContent =
          "Run failed before summary generation.";
      } else if (runStatus === "partial") {
        elements.summaryText.textContent =
          "Summary failed, but structured data is available.";
      } else {
        elements.summaryText.textContent =
          "Summary pending (run not completed yet).";
      }
    } else {
      elements.summaryText.textContent = "No summary generated yet.";
    }
    return;
  }
  text
    .split(/\n+/)
    .filter((part) => part.trim())
    .forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part.trim();
      elements.summaryText.appendChild(p);
    });
}

function renderSummary(bundle) {
  const variant = state.summaryVariant || "summary_text";
  const text = summaryTextForVariant(bundle, variant);
  renderParagraphs(text, bundle ? bundle.run_status : null);
}

function renderAskAnswer(text) {
  if (!elements.askAnswer) return;
  clearNode(elements.askAnswer);
  if (!text) {
    elements.askAnswer.textContent = "No answer yet.";
    return;
  }
  text
    .split(/\n+/)
    .filter((part) => part.trim())
    .forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part.trim();
      elements.askAnswer.appendChild(p);
    });
}

function renderAskCitations(citations) {
  if (!elements.askCitations) return;
  clearNode(elements.askCitations);
  if (!citations || citations.length === 0) {
    elements.askCitations.textContent = "No citations returned.";
    return;
  }
  citations.forEach((citation, index) => {
    const card = document.createElement("div");
    card.className = "citation-card";
    const title = document.createElement("h4");
    title.textContent = `Citation ${index + 1}`;
    const quote = document.createElement("p");
    quote.textContent = citation.quote || "Citation available.";
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = citation.note || citation.utterance_id || "";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.textContent = "View evidence";
    button.addEventListener("click", () => {
      const evidence = [
        {
          utterance_id: citation.utterance_id,
          kind: "support",
        },
      ];
      openEvidence("Answer evidence", evidence);
    });
    card.append(title, quote, meta, button);
    elements.askCitations.appendChild(card);
  });
}

function clearAskPanel() {
  renderAskAnswer("");
  if (elements.askCitations) {
    clearNode(elements.askCitations);
  }
}

function updateSummaryVariantOptions(bundle) {
  const select = elements.summaryVariant;
  if (!select) return;
  const variants = availableSummaryVariants(bundle);
  clearNode(select);
  if (variants.length === 0) {
    select.disabled = true;
    state.summaryVariant = "summary_text";
    return;
  }
  variants.forEach((variant) => {
    const option = document.createElement("option");
    option.value = variant;
    option.textContent = summaryVariantLabel(variant);
    select.appendChild(option);
  });
  if (!variants.includes(state.summaryVariant)) {
    state.summaryVariant = variants[0];
  }
  select.value = state.summaryVariant;
  select.disabled = false;
}

function renderMetrics(bundle) {
  clearNode(elements.runMetrics);
  if (!bundle) return;
  const metrics = [
    `Run ${bundle.run_id ? bundle.run_id.slice(0, 8) : "n/a"}`,
    bundle.run_status ? `Status ${bundle.run_status}` : null,
    `${bundle.scenes ? bundle.scenes.length : 0} scenes`,
    `${bundle.events ? bundle.events.length : 0} events`,
    `${bundle.threads ? bundle.threads.length : 0} threads`,
    `${bundle.quotes ? bundle.quotes.length : 0} quotes`,
    `${bundle.entities ? bundle.entities.length : 0} entities`,
  ].filter(Boolean);
  metrics.forEach((metric) => {
    const badge = document.createElement("span");
    badge.textContent = metric;
    elements.runMetrics.appendChild(badge);
  });
}

function renderRunProgress(statusPayload) {
  clearNode(elements.runProgress);
  if (!statusPayload) {
    return;
  }
  const header = document.createElement("div");
  header.className = "run-status";
  header.textContent = statusPayload.status
    ? `Run status: ${statusPayload.status}`
    : "Run status: n/a";
  elements.runProgress.appendChild(header);

  const steps = statusPayload.steps || [];
  if (steps.length === 0) {
    return;
  }
  steps.forEach((step) => {
    const row = document.createElement("div");
    row.className = `run-step ${step.status || ""}`;
    const name = document.createElement("span");
    name.textContent = step.name || "step";
    const stateText = document.createElement("span");
    stateText.textContent = step.status || "unknown";
    row.appendChild(name);
    row.appendChild(stateText);
    elements.runProgress.appendChild(row);
  });
}

function renderQuality(bundle) {
  clearNode(elements.qualityMetrics);
  if (!bundle || !bundle.quality) {
    return;
  }
  const quality = bundle.quality || {};
  const metrics = [
    ["Mentions missing evidence", quality.mentions_missing_evidence],
    ["Scenes missing evidence", quality.scenes_missing_evidence],
    ["Events missing evidence", quality.events_missing_evidence],
    ["Threads missing evidence", quality.threads_missing_evidence],
    ["Thread updates missing evidence", quality.thread_updates_missing_evidence],
  ];
  const title = document.createElement("h3");
  title.textContent = "Quality Checks";
  elements.qualityMetrics.appendChild(title);
  metrics.forEach(([label, value]) => {
    if (value == null) return;
    const row = document.createElement("div");
    row.className = "quality-row";
    const name = document.createElement("span");
    name.textContent = label;
    const count = document.createElement("strong");
    count.textContent = String(value);
    row.appendChild(name);
    row.appendChild(count);
    elements.qualityMetrics.appendChild(row);
  });
}

function renderDiagnostics(bundle) {
  clearNode(elements.runDiagnostics);
  if (!bundle) return;
  const metrics = bundle.metrics || {};
  const calls = bundle.llm_calls || [];
  const usage = bundle.llm_usage || [];

  const header = document.createElement("h3");
  header.textContent = "Run Diagnostics";
  elements.runDiagnostics.appendChild(header);

  if (Object.keys(metrics).length > 0) {
    const metricList = document.createElement("div");
    metricList.className = "diagnostic-grid";
    Object.entries(metrics).forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "diagnostic-row";
      const name = document.createElement("span");
      name.textContent = key.replace(/_/g, " ");
      const count = document.createElement("strong");
      count.textContent = String(value);
      row.appendChild(name);
      row.appendChild(count);
      metricList.appendChild(row);
    });
    elements.runDiagnostics.appendChild(metricList);
  }

  if (usage.length > 0) {
    const usageHeader = document.createElement("h4");
    usageHeader.textContent = "Token Usage";
    elements.runDiagnostics.appendChild(usageHeader);

    const totals = usage.reduce(
      (acc, entry) => {
        acc.prompt += entry.prompt_token_count || 0;
        acc.cached += entry.cached_content_token_count || 0;
        acc.candidates += entry.candidates_token_count || 0;
        acc.total += entry.total_token_count || 0;
        acc.cost += entry.total_cost_usd || 0;
        return acc;
      },
      { prompt: 0, cached: 0, candidates: 0, total: 0, cost: 0 }
    );

    const totalRow = document.createElement("div");
    totalRow.className = "diagnostic-row";
    const totalLabel = document.createElement("span");
    totalLabel.textContent = "Total tokens";
    const totalValue = document.createElement("strong");
    totalValue.textContent = `${totals.total} (cached ${totals.cached})`;
    totalRow.appendChild(totalLabel);
    totalRow.appendChild(totalValue);
    elements.runDiagnostics.appendChild(totalRow);

    if (totals.cost > 0) {
      const costRow = document.createElement("div");
      costRow.className = "diagnostic-row";
      const costLabel = document.createElement("span");
      costLabel.textContent = "Estimated cost";
      const costValue = document.createElement("strong");
      costValue.textContent = `$${totals.cost.toFixed(4)}`;
      costRow.appendChild(costLabel);
      costRow.appendChild(costValue);
      elements.runDiagnostics.appendChild(costRow);
    }

    const usageList = document.createElement("div");
    usageList.className = "diagnostic-list";
    usage.forEach((entry) => {
      const item = document.createElement("div");
      item.className = "diagnostic-item";
      const title = document.createElement("div");
      title.className = "diagnostic-title";
      title.textContent = entry.call_kind || "llm_call";
      const meta = document.createElement("div");
      meta.className = "meta";
      const cost =
        entry.total_cost_usd != null ? ` • cost $${entry.total_cost_usd.toFixed(4)}` : "";
      meta.textContent = `prompt ${entry.prompt_token_count || 0} • cached ${
        entry.cached_content_token_count || 0
      } • output ${entry.candidates_token_count || 0}${cost}`;
      item.appendChild(title);
      item.appendChild(meta);
      usageList.appendChild(item);
    });
    elements.runDiagnostics.appendChild(usageList);
  }

  if (calls.length > 0) {
    const callHeader = document.createElement("h4");
    callHeader.textContent = "LLM Calls";
    elements.runDiagnostics.appendChild(callHeader);
    const list = document.createElement("div");
    list.className = "diagnostic-list";
    calls.forEach((call) => {
      const item = document.createElement("div");
      item.className = `diagnostic-item ${call.status}`;
      const title = document.createElement("div");
      title.className = "diagnostic-title";
      title.textContent = `${call.kind} • ${call.model}`;
      const meta = document.createElement("div");
      meta.className = "meta";
      const latency = call.latency_ms != null ? `${call.latency_ms}ms` : "n/a";
      meta.textContent = `${call.prompt_id}@${call.prompt_version} • ${latency}`;
      item.appendChild(title);
      item.appendChild(meta);
      if (call.error) {
        const error = document.createElement("div");
        error.className = "diagnostic-error";
        error.textContent = call.error;
        item.appendChild(error);
      }
      list.appendChild(item);
    });
    elements.runDiagnostics.appendChild(list);
  }

  if (Object.keys(metrics).length === 0 && calls.length === 0 && usage.length === 0) {
    const empty = document.createElement("p");
    empty.className = "meta";
    empty.textContent = "No diagnostics available for this run.";
    elements.runDiagnostics.appendChild(empty);
  }
}

function stopRunStatusPolling() {
  if (state.runStatusTimer) {
    clearTimeout(state.runStatusTimer);
    state.runStatusTimer = null;
  }
}

async function pollRunStatus(sessionId, runId) {
  if (!sessionId) return;
  try {
    const query = runId ? `?run_id=${runId}` : "";
    const statusPayload = await fetchJson(`/sessions/${sessionId}/run-status${query}`);
    renderRunProgress(statusPayload);
    if (statusPayload && statusPayload.status === "running") {
      state.runStatusTimer = setTimeout(() => pollRunStatus(sessionId, runId), 3000);
      return;
    }
    if (
      statusPayload &&
      (statusPayload.status === "completed" || statusPayload.status === "partial")
    ) {
      await loadBundle(sessionId, runId, { skipStatusPolling: true });
    }
  } catch (err) {
    console.error(err);
  }
}

function startRunStatusPolling(sessionId, runId) {
  stopRunStatusPolling();
  pollRunStatus(sessionId, runId);
}

function canRunSession() {
  return !state.authEnabled || state.userRole === "dm";
}

async function setCurrentRun(sessionId, runId) {
  if (!sessionId || !runId || !canRunSession()) {
    return null;
  }
  const headers = {};
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(
    `${API_BASE}/sessions/${sessionId}/current-run?run_id=${encodeURIComponent(runId)}`,
    {
      method: "PUT",
      headers,
    }
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function exportSession(sessionId) {
  if (!sessionId) return;
  const headers = {};
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/export`, {
    method: "GET",
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `session_${sessionId}_export.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function deleteSession(sessionId) {
  if (!sessionId) return;
  const headers = {};
  if (state.currentUserId) {
    headers["X-User-Id"] = state.currentUserId;
  }
  const response = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: "DELETE",
    headers,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Delete failed: ${response.status}`);
  }
  return response.json();
}

async function waitForLatestRun(sessionId, previousRunId, attempts = 10) {
  for (let i = 0; i < attempts; i += 1) {
    const runs = await fetchJson(`/sessions/${sessionId}/runs`);
    if (runs && runs.length > 0) {
      const latestId = runs[0].id;
      if (!previousRunId || latestId !== previousRunId) {
        return latestId;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return null;
}

function renderArtifacts(artifacts) {
  clearNode(elements.artifactLinks);
  if (!artifacts || artifacts.length === 0) {
    return;
  }
  artifacts.forEach((artifact) => {
    const link = document.createElement("a");
    link.href = `/artifacts/${artifact.id}`;
    link.textContent = artifactLabel(artifact.kind);
    link.target = "_blank";
    elements.artifactLinks.appendChild(link);
  });
}

function renderThreads(threads) {
  clearNode(elements.threadList);
  if (!threads || threads.length === 0) {
    elements.threadList.textContent = "No active threads found.";
    return;
  }
  threads.forEach((thread) => {
    const card = document.createElement("div");
    card.className = "thread-card";
    const title = document.createElement("h3");
    title.textContent = thread.title;
    card.appendChild(title);
    if (thread.summary) {
      const summary = document.createElement("p");
      summary.textContent = thread.summary;
      summary.className = "meta";
      card.appendChild(summary);
    }
    const status = document.createElement("span");
    status.className = "thread-status";
    status.textContent = thread.status || "active";
    card.appendChild(status);

    const tagRow = document.createElement("div");
    tagRow.className = "tag-row";
    if (thread.corrected) {
      const tag = document.createElement("span");
      tag.className = "tag correction";
      tag.textContent = "Corrected";
      tagRow.appendChild(tag);
    }
    if (thread.confidence != null) {
      const tag = document.createElement("span");
      tag.className = "tag confidence";
      const percent = Math.round(thread.confidence * 100);
      tag.textContent = `Confidence ${percent}%`;
      tagRow.appendChild(tag);
    }
    if (tagRow.childElementCount > 0) {
      card.appendChild(tagRow);
    }

    if (thread.updates && thread.updates.length > 0) {
      const updates = document.createElement("ul");
      updates.className = "thread-updates";
      thread.updates.forEach((update) => {
        const li = document.createElement("li");
        li.textContent = update.note || update.update_type;
        updates.appendChild(li);
      });
      card.appendChild(updates);
    }

    const evidence = collectEvidence(thread.evidence, thread.updates || []);
    if (evidence.length > 0) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Evidence";
      button.addEventListener("click", () =>
        openEvidence(`Thread: ${thread.title}`, evidence)
      );
      card.appendChild(button);
    }
    elements.threadList.appendChild(card);
  });
}

function renderScenes(scenes) {
  clearNode(elements.sceneList);
  if (!scenes || scenes.length === 0) {
    elements.sceneList.textContent = "No scenes yet.";
    return;
  }
  scenes.forEach((scene) => {
    const card = document.createElement("div");
    card.className = "scene-card";
    const title = document.createElement("h3");
    title.textContent = scene.title || "Scene";
    card.appendChild(title);
    const summary = document.createElement("p");
    summary.textContent = scene.summary;
    card.appendChild(summary);
    const meta = document.createElement("p");
    meta.className = "meta";
    const time = `${formatTime(scene.start_ms)} - ${formatTime(scene.end_ms)}`.trim();
    meta.textContent = [scene.location, time].filter(Boolean).join(" | ");
    card.appendChild(meta);
    if (scene.evidence && scene.evidence.length > 0) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Evidence";
      button.addEventListener("click", () =>
        openEvidence(`Scene: ${scene.title || "Scene"}`, scene.evidence)
      );
      card.appendChild(button);
    }
    elements.sceneList.appendChild(card);
  });
}

function renderEvents(events) {
  clearNode(elements.eventList);
  if (!events || events.length === 0) {
    elements.eventList.textContent = "No events captured.";
    return;
  }
  const canBookmark = !state.authEnabled || state.currentUserId;
  const canEdit = !state.authEnabled || state.userRole === "dm";
  events.forEach((event) => {
    const card = document.createElement("div");
    card.className = "event-card";
    const title = document.createElement("h3");
    title.textContent = event.summary;
    card.appendChild(title);
    const type = document.createElement("span");
    type.className = "event-type";
    type.textContent = event.event_type;
    card.appendChild(type);
    const time = document.createElement("p");
    time.className = "meta";
    time.textContent = `${formatTime(event.start_ms)} - ${formatTime(event.end_ms)}`;
    card.appendChild(time);
    const row = document.createElement("div");
    row.className = "tag-row";
    if (event.entities && event.entities.length > 0) {
      event.entities.forEach((entity) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = entity;
        row.appendChild(tag);
      });
    }
    if (event.confidence != null) {
      const tag = document.createElement("span");
      tag.className = "tag confidence";
      const percent = Math.round(event.confidence * 100);
      tag.textContent = `Confidence ${percent}%`;
      row.appendChild(tag);
    }
    if (row.childElementCount > 0) {
      card.appendChild(row);
    }
    if (event.evidence && event.evidence.length > 0) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Evidence";
      button.addEventListener("click", () =>
        openEvidence(`Event: ${event.event_type}`, event.evidence)
      );
      card.appendChild(button);
    }
    if (canBookmark) {
      const bookmarkButton = document.createElement("button");
      bookmarkButton.type = "button";
      bookmarkButton.textContent = "Bookmark";
      bookmarkButton.addEventListener("click", () =>
        saveBookmark("event", event.id)
      );
      card.appendChild(bookmarkButton);
    }
    if (canEdit) {
      const spoilerButton = document.createElement("button");
      spoilerButton.type = "button";
      spoilerButton.textContent = "Spoiler";
      spoilerButton.addEventListener("click", () =>
        applySpoiler("event", event.id)
      );
      card.appendChild(spoilerButton);
    }
    elements.eventList.appendChild(card);
  });
}

function renderQuotes(quotes) {
  clearNode(elements.quoteList);
  if (!quotes || quotes.length === 0) {
    elements.quoteList.textContent = "No notable quotes captured.";
    return;
  }
  const canEdit = !state.authEnabled || state.userRole === "dm";
  const canBookmark = !state.authEnabled || state.currentUserId;
  quotes.forEach((quote) => {
    const card = document.createElement("div");
    card.className = "quote-card";
    const block = document.createElement("blockquote");
    block.textContent = `"${quote.display_text || quote.clean_text || ""}"`;
    card.appendChild(block);
    const footer = document.createElement("footer");
    const timecode = timecodeForUtterance(quote.utterance_id);
    const note = quote.note ? `- ${quote.note}` : "";
    footer.textContent = [quote.speaker || "Unknown", note, timecode]
      .filter(Boolean)
      .join(" ");
    card.appendChild(footer);
    const evidence = [
      {
        utterance_id: quote.utterance_id,
        char_start: quote.char_start,
        char_end: quote.char_end,
      },
    ];
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Evidence";
    button.addEventListener("click", () =>
      openEvidence(`Quote: ${quote.speaker || "Unknown"}`, evidence)
    );
    card.appendChild(button);
    if (canBookmark) {
      const bookmarkButton = document.createElement("button");
      bookmarkButton.type = "button";
      bookmarkButton.textContent = "Bookmark";
      bookmarkButton.addEventListener("click", () =>
        saveBookmark("quote", quote.id)
      );
      card.appendChild(bookmarkButton);
    }
    if (canEdit) {
      const redactButton = document.createElement("button");
      redactButton.type = "button";
      redactButton.className = "danger";
      redactButton.textContent = "Redact quote";
      redactButton.addEventListener("click", () =>
        applyRedaction("quote", quote.id, "this quote")
      );
      card.appendChild(redactButton);
    }
    elements.quoteList.appendChild(card);
  });
}

function renderTranscript(lines) {
  if (!elements.transcriptText) return;
  if (!lines || lines.length === 0) {
    elements.transcriptText.textContent = "Transcript not available.";
    return;
  }
  elements.transcriptText.textContent = lines.join("\n");
}

function renderEntities(entities) {
  clearNode(elements.entityList);
  if (!entities || entities.length === 0) {
    elements.entityList.textContent = "No entities in this session.";
    return;
  }
  const filter = elements.entityFilter.value;
  const filtered = entities.filter((entity) => {
    if (filter === "all") return true;
    return entity.type === filter;
  });
  if (filtered.length === 0) {
    elements.entityList.textContent = "No entities match the filter.";
    return;
  }
  filtered.forEach((entity) => {
    const card = document.createElement("div");
    card.className = "entity-card";
    const title = document.createElement("h3");
    title.textContent = entity.name;
    card.appendChild(title);
    const type = document.createElement("p");
    type.textContent = entity.type;
    card.appendChild(type);
    if (entity.description) {
      const desc = document.createElement("p");
      desc.textContent = entity.description;
      card.appendChild(desc);
    }
    if (entity.corrected) {
      const tagRow = document.createElement("div");
      tagRow.className = "tag-row";
      const tag = document.createElement("span");
      tag.className = "tag correction";
      tag.textContent = "Corrected";
      tagRow.appendChild(tag);
      card.appendChild(tagRow);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open dossier";
    button.addEventListener("click", () => openEntity(entity));
    card.appendChild(button);
    elements.entityList.appendChild(card);
  });
}

function renderQuestJournal(threads) {
  clearNode(elements.questList);
  if (!threads || threads.length === 0) {
    elements.questList.textContent = "No quests found for this campaign.";
    return;
  }
  const canEdit = !state.authEnabled || state.userRole === "dm";
  threads.forEach((thread) => {
    const card = document.createElement("div");
    card.className = "thread-card";
    const title = document.createElement("h3");
    title.textContent = thread.title;
    card.appendChild(title);
    if (thread.summary) {
      const summary = document.createElement("p");
      summary.textContent = thread.summary;
      summary.className = "meta";
      card.appendChild(summary);
    }
    const status = document.createElement("span");
    status.className = "thread-status";
    status.textContent = thread.status || "active";
    card.appendChild(status);
    const tagRow = document.createElement("div");
    tagRow.className = "tag-row";
    if (thread.corrected) {
      const tag = document.createElement("span");
      tag.className = "tag correction";
      tag.textContent = "Corrected";
      tagRow.appendChild(tag);
    }
    if (thread.confidence != null) {
      const tag = document.createElement("span");
      tag.className = "tag confidence";
      const percent = Math.round(thread.confidence * 100);
      tag.textContent = `Confidence ${percent}%`;
      tagRow.appendChild(tag);
    }
    if (tagRow.childElementCount > 0) {
      card.appendChild(tagRow);
    }
    if (thread.updates && thread.updates.length > 0) {
      const updates = document.createElement("ul");
      updates.className = "thread-updates";
      thread.updates.slice(0, 3).forEach((update) => {
        const li = document.createElement("li");
        li.textContent = update.note || update.update_type;
        updates.appendChild(li);
      });
      card.appendChild(updates);
    }
    if (canEdit) {
      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.textContent = "Edit quest";
      editButton.addEventListener("click", () => openThread(thread));
      card.appendChild(editButton);
    }
    if (thread.session_id) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Open session";
      button.addEventListener("click", () => jumpToSession(thread.session_id));
      card.appendChild(button);
    }
    elements.questList.appendChild(card);
  });
}

function renderCodex(entities) {
  clearNode(elements.codexList);
  if (!entities || entities.length === 0) {
    elements.codexList.textContent = "No campaign entities found.";
    return;
  }
  const filter = elements.codexFilter.value;
  const query = elements.codexSearch.value.trim().toLowerCase();
  const filtered = entities.filter((entity) => {
    if (filter !== "all" && entity.type !== filter) {
      return false;
    }
    if (query) {
      const hay = `${entity.name} ${entity.description || ""}`.toLowerCase();
      return hay.includes(query);
    }
    return true;
  });
  if (filtered.length === 0) {
    elements.codexList.textContent = "No codex entries match the filter.";
    return;
  }
  filtered.forEach((entity) => {
    const card = document.createElement("div");
    card.className = "entity-card";
    const title = document.createElement("h3");
    title.textContent = entity.name;
    card.appendChild(title);
    const type = document.createElement("p");
    type.textContent = entity.type;
    card.appendChild(type);
    if (entity.description) {
      const desc = document.createElement("p");
      desc.textContent = entity.description;
      card.appendChild(desc);
    }
    if (entity.corrected) {
      const tagRow = document.createElement("div");
      tagRow.className = "tag-row";
      const tag = document.createElement("span");
      tag.className = "tag correction";
      tag.textContent = "Corrected";
      tagRow.appendChild(tag);
      card.appendChild(tagRow);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open dossier";
    button.addEventListener("click", () => openEntity(entity));
    card.appendChild(button);
    elements.codexList.appendChild(card);
  });
}

function renderTimeline(scenes, events) {
  clearNode(elements.timelineList);
  if ((!scenes || scenes.length === 0) && (!events || events.length === 0)) {
    elements.timelineList.textContent =
      "Timeline will appear once scenes/events are available.";
    return;
  }
  const entries = [];
  scenes.forEach((scene) => {
    entries.push({
      start: scene.start_ms || 0,
      type: "Scene",
      title: scene.title || "Scene",
      detail: scene.summary,
    });
  });
  events.forEach((event) => {
    entries.push({
      start: event.start_ms || 0,
      type: event.event_type,
      title: event.summary,
      detail: null,
    });
  });
  entries.sort((a, b) => a.start - b.start);
  entries.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "timeline-card";
    const time = document.createElement("div");
    time.className = "timeline-time";
    time.textContent = formatTime(entry.start);
    const body = document.createElement("div");
    const title = document.createElement("h3");
    title.className = "timeline-title";
    title.textContent = entry.title;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = entry.type;
    body.appendChild(title);
    if (entry.detail) {
      const p = document.createElement("p");
      p.textContent = entry.detail;
      body.appendChild(p);
    }
    body.appendChild(meta);
    card.appendChild(time);
    card.appendChild(body);
    elements.timelineList.appendChild(card);
  });
}

function collectEvidence(threadEvidence, updates) {
  const evidence = [];
  if (threadEvidence && threadEvidence.length > 0) {
    evidence.push(...threadEvidence);
  }
  updates.forEach((update) => {
    if (update.evidence && update.evidence.length > 0) {
      evidence.push(...update.evidence);
    }
  });
  return evidence;
}

function renderSessionMeta(session) {
  if (!session) {
    elements.sessionMeta.textContent = "";
    return;
  }
  const bits = [];
  if (session.session_number != null) {
    bits.push(`Session ${session.session_number}`);
  }
  if (session.title) {
    bits.push(session.title);
  }
  if (session.occurred_at) {
    bits.push(new Date(session.occurred_at).toLocaleDateString());
  }
  elements.sessionMeta.textContent = bits.join(" | ");
}

function renderSessions() {
  clearNode(elements.sessionList);
  elements.sessionCount.textContent = state.sessions.length;
  state.sessions.forEach((session) => {
    const card = document.createElement("div");
    card.className = "session-card";
    if (session.id === state.selectedSession) {
      card.classList.add("active");
    }
    const title = document.createElement("h3");
    const label = session.session_number ? `Session ${session.session_number}` : session.slug;
    title.textContent = label;
    const meta = document.createElement("p");
    meta.textContent = session.title || "";
    card.appendChild(title);
    card.appendChild(meta);
    if (session.latest_run_status) {
      const status = document.createElement("span");
      status.className = `session-status ${session.latest_run_status}`;
      status.textContent = session.latest_run_status;
      card.appendChild(status);
    }
    card.addEventListener("click", () => loadSession(session.id));
    elements.sessionList.appendChild(card);
  });
}

function renderBundle(bundle) {
  if (!bundle) {
    return;
  }
  state.transcriptLines = bundle.transcript?.lines || [];
  state.utteranceTimecodes = bundle.transcript?.utterance_timecodes || {};
  updateSummaryVariantOptions(bundle);
  renderMetrics(bundle);
  renderRunProgress(null);
  renderSummary(bundle);
  renderQuality(bundle);
  renderDiagnostics(bundle);
  updateDownload(bundle);
  renderArtifacts(bundle.artifacts || []);
  renderThreads(bundle.threads || []);
  renderScenes(bundle.scenes || []);
  renderEvents(bundle.events || []);
  renderQuotes(bundle.quotes || []);
  renderTranscript(state.transcriptLines);
  renderEntities(bundle.entities || []);
  renderTimeline(bundle.scenes || [], bundle.events || []);
}

function updateDownload(bundle) {
  const button = elements.downloadSummary;
  const formatSelect = elements.summaryFormat;
  if (!button || !formatSelect) return;
  button.disabled = true;
  button.dataset.mode = "";
  button.dataset.href = "";
  button.dataset.filename = "";

  if (!bundle) {
    button.textContent = "Download Summary";
    formatSelect.disabled = true;
    clearNode(formatSelect);
    return;
  }

  const variant = state.summaryVariant || "summary_text";
  const artifacts = bundle.artifacts || [];
  const prefix = variant === "summary_text" ? "summary" : variant;
  const docx = artifacts.find((item) => item.kind === `${prefix}_docx`);
  const txt = artifacts.find((item) => item.kind === `${prefix}_txt`);
  const inlineText = summaryTextForVariant(bundle, variant);
  const session = state.sessionMap[state.selectedSession] || {};
  const slug = session.slug || "summary";
  const variantSlug = summaryVariantSlug(variant);

  const options = [];
  if (docx) {
    options.push({ value: "docx", label: "DOCX", artifact: docx, ext: "docx" });
  }
  if (txt) {
    options.push({ value: "txt", label: "TXT", artifact: txt, ext: "txt" });
  }
  if (inlineText) {
    options.push({ value: "inline", label: "Inline", ext: "txt" });
  }

  clearNode(formatSelect);
  if (options.length === 0) {
    formatSelect.disabled = true;
    button.textContent = "Download Summary";
    return;
  }

  options.forEach((option) => {
    const optionEl = document.createElement("option");
    optionEl.value = option.value;
    optionEl.textContent = option.label;
    formatSelect.appendChild(optionEl);
  });
  formatSelect.disabled = false;

  const selected =
    options.find((option) => option.value === state.summaryFormat) || options[0];
  state.summaryFormat = selected.value;
  formatSelect.value = selected.value;

  const filename = `${slug}.${variantSlug}.${selected.ext}`;
  if (selected.value === "inline") {
    button.textContent = "Download TXT";
    button.dataset.mode = "inline";
    button.dataset.filename = filename;
    button.disabled = false;
    return;
  }
  button.textContent = `Download ${selected.label}`;
  button.dataset.mode = "artifact";
  button.dataset.href = `/artifacts/${selected.artifact.id}`;
  button.dataset.filename = filename;
  button.disabled = false;
}

async function loadCampaigns() {
  setStatus("Loading campaigns...");
  try {
    const data = await fetchJson("/campaigns");
    state.campaigns = data;
    clearNode(elements.campaignSelect);
    data.forEach((campaign) => {
      const option = document.createElement("option");
      option.value = campaign.slug;
      option.textContent = campaign.name || campaign.slug;
      elements.campaignSelect.appendChild(option);
    });
    if (data.length > 0) {
      state.selectedCampaign = data[0].slug;
      elements.campaignSelect.value = state.selectedCampaign;
      await loadSessions();
    } else {
      setStatus("No campaigns found.");
    }
  } catch (err) {
    setStatus("Unable to load campaigns. Set a user id if auth is enabled.");
    console.error(err);
  }
}

async function createSessionFromForm() {
  if (!state.selectedCampaign) {
    setStatus("Select a campaign before creating a session.");
    return;
  }
  const slug = elements.newSessionSlug.value.trim();
  const title = elements.newSessionTitle.value.trim();
  const occurredAt = elements.newSessionDate.value;
  const numberRaw = elements.newSessionNumber.value;
  if (!slug || !title || !occurredAt) {
    setStatus("Session slug, title, and date are required.");
    return;
  }
  const payload = { slug, title, occurred_at: occurredAt };
  if (numberRaw) {
    const num = Number.parseInt(numberRaw, 10);
    if (Number.isFinite(num)) {
      payload.session_number = num;
    }
  }
  setStatus("Creating session...");
  try {
    const created = await postJson(`/campaigns/${state.selectedCampaign}/sessions`, payload);
    const file = elements.newSessionFile.files?.[0];
    if (file) {
      setStatus("Uploading transcript...");
      await uploadTranscript(state.selectedCampaign, slug, file);
    }
    elements.newSessionSlug.value = "";
    elements.newSessionTitle.value = "";
    elements.newSessionDate.value = "";
    elements.newSessionNumber.value = "";
    if (elements.newSessionFile) {
      elements.newSessionFile.value = "";
    }
    await loadSessions();
    if (created?.id) {
      await loadSession(created.id);
    }
    setStatus("Session created.");
  } catch (err) {
    console.error(err);
    setStatus("Failed to create session.");
  }
}

async function loadSessions() {
  if (!state.selectedCampaign) {
    return;
  }
  setStatus("Loading sessions...");
  const sessions = await fetchJson(`/campaigns/${state.selectedCampaign}/sessions`);
  state.sessions = sessions;
  state.sessionMap = Object.fromEntries(sessions.map((s) => [s.id, s]));
  renderSessions();
  clearNode(elements.runSelect);
  elements.sessionOnlyToggle.disabled = true;
  await loadUserRole();
  await loadQuestJournal();
  await loadCodex();
  setStatus("Select a session to begin.");
}

async function loadNotesAndBookmarks() {
  if (!state.selectedCampaign || !state.selectedSession) {
    return;
  }
  try {
    const noteQuery = new URLSearchParams({
      campaign_slug: state.selectedCampaign,
      session_id: state.selectedSession,
    });
    const bookmarkQuery = new URLSearchParams({
      campaign_slug: state.selectedCampaign,
      session_id: state.selectedSession,
    });
    const [notes, bookmarks] = await Promise.all([
      fetchJson(`/notes?${noteQuery.toString()}`),
      fetchJson(`/bookmarks?${bookmarkQuery.toString()}`),
    ]);
    renderNotes(notes);
    renderBookmarks(bookmarks);
  } catch (err) {
    if (elements.noteList) {
      elements.noteList.textContent = "Failed to load notes.";
    }
    if (elements.bookmarkList) {
      elements.bookmarkList.textContent = "Failed to load bookmarks.";
    }
    console.error(err);
  }
}

function renderNotes(notes) {
  if (!elements.noteList) return;
  clearNode(elements.noteList);
  if (!notes || notes.length === 0) {
    elements.noteList.textContent = "No notes yet.";
    return;
  }
  notes.forEach((note) => {
    const card = document.createElement("div");
    card.className = "note-card";
    const body = document.createElement("p");
    body.textContent = note.body;
    const meta = document.createElement("small");
    const created = note.created_at ? new Date(note.created_at).toLocaleString() : "";
    meta.textContent = created;
    card.appendChild(body);
    card.appendChild(meta);
    elements.noteList.appendChild(card);
  });
}

function renderBookmarks(bookmarks) {
  if (!elements.bookmarkList) return;
  clearNode(elements.bookmarkList);
  if (!bookmarks || bookmarks.length === 0) {
    elements.bookmarkList.textContent = "No bookmarks yet.";
    return;
  }
  const quoteLookup = new Map((state.bundle?.quotes || []).map((q) => [q.id, q]));
  const eventLookup = new Map((state.bundle?.events || []).map((e) => [e.id, e]));
  bookmarks.forEach((bookmark) => {
    const card = document.createElement("div");
    card.className = "note-card";
    let text = `${bookmark.target_type} ${bookmark.target_id}`;
    if (bookmark.target_type === "quote") {
      const quote = quoteLookup.get(bookmark.target_id);
      if (quote) {
        text = quote.display_text || quote.clean_text || text;
      }
    } else if (bookmark.target_type === "event") {
      const event = eventLookup.get(bookmark.target_id);
      if (event) {
        text = event.summary || event.event_type || text;
      }
    }
    const body = document.createElement("p");
    body.textContent = text;
    const meta = document.createElement("small");
    const created = bookmark.created_at
      ? new Date(bookmark.created_at).toLocaleString()
      : "";
    meta.textContent = created;
    card.appendChild(body);
    card.appendChild(meta);
    elements.bookmarkList.appendChild(card);
  });
}

async function loadQuestJournal() {
  if (!state.selectedCampaign) return;
  const status = elements.questFilter.value;
  const params = new URLSearchParams();
  if (status && status !== "all") {
    params.set("status", status);
  }
  if (state.selectedSession) {
    params.set("session_id", state.selectedSession);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  try {
    const threads = await fetchJson(`/campaigns/${state.selectedCampaign}/threads${query}`);
    state.questThreads = threads;
    renderQuestJournal(threads);
  } catch (err) {
    clearNode(elements.questList);
    elements.questList.textContent = "Failed to load quest journal.";
    console.error(err);
  }
}

async function loadCodex() {
  if (!state.selectedCampaign) return;
  try {
    const params = new URLSearchParams();
    if (state.selectedSession) {
      params.set("session_id", state.selectedSession);
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    const entities = await fetchJson(`/campaigns/${state.selectedCampaign}/entities${query}`);
    state.campaignEntities = entities;
    renderCodex(entities);
  } catch (err) {
    clearNode(elements.codexList);
    elements.codexList.textContent = "Failed to load campaign codex.";
    console.error(err);
  }
}

async function loadSession(sessionId) {
  if (!sessionId) {
    return;
  }
  state.selectedSession = sessionId;
  updateRunControls();
  elements.sessionOnlyToggle.disabled = false;
  state.selectedRun = null;
  renderSessions();
  const session = state.sessionMap[sessionId];
  renderSessionMeta(session);
  clearAskPanel();
  setStatus("Loading session runs...");
  const runs = await fetchJson(`/sessions/${sessionId}/runs`);
  const activeRun = populateRunSelect(runs);
  state.selectedRun = activeRun;
  await loadQuestJournal();
  await loadCodex();
  await loadBundle(sessionId, activeRun);
}

async function jumpToSession(sessionId) {
  if (!sessionId) return;
  await loadSession(sessionId);
  closeSearch();
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function fetchUtterances(ids) {
  const params = ids.map((id) => `ids=${encodeURIComponent(id)}`).join("&");
  return fetchJson(`/utterances?${params}`);
}

function highlightSpan(text, start, end) {
  if (start == null || end == null || end <= start) {
    return escapeHtml(text);
  }
  const prefixRaw = text.slice(0, start);
  const middleRaw = text.slice(start, end);
  const suffixRaw = text.slice(end);
  const prefix = escapeHtml(prefixRaw);
  const middle = escapeHtml(middleRaw);
  const suffix = escapeHtml(suffixRaw);
  return `${prefix}<mark>${middle}</mark>${suffix}`;
}

async function openEvidence(title, evidence) {
  elements.evidenceTitle.textContent = title;
  elements.evidenceMeta.textContent = `${evidence.length} evidence spans`;
  clearNode(elements.evidenceDetails);
  elements.evidencePanel.classList.remove("hidden");
  const canEdit = !state.authEnabled || state.userRole === "dm";
  const ids = [...new Set(evidence.map((ev) => ev.utterance_id).filter(Boolean))];
  if (ids.length === 0) {
    elements.evidenceDetails.appendChild(
      renderSearchItem("No evidence spans available.", null)
    );
    return;
  }
  try {
    const utterances = await fetchUtterances(ids);
    const lookup = new Map(utterances.map((utt) => [utt.id, utt]));
    evidence.forEach((ev) => {
      const utt = lookup.get(ev.utterance_id);
      if (!utt) {
        return;
      }
      const item = document.createElement("div");
      item.className = "search-item";
      const html = highlightSpan(utt.text, ev.char_start, ev.char_end);
      item.innerHTML = html;
      const meta = document.createElement("small");
      const timecode = timecodeForUtterance(utt.id, utt.start_ms);
      const range = `${formatTimecode(utt.start_ms)} - ${formatTimecode(utt.end_ms)}`;
      meta.textContent = [timecode, range].filter(Boolean).join(" • ");
      item.appendChild(meta);
      if (canEdit) {
        const redact = document.createElement("button");
        redact.type = "button";
        redact.className = "danger";
        redact.textContent = "Redact utterance";
        redact.addEventListener("click", () =>
          applyRedaction("utterance", utt.id, "this utterance")
        );
        item.appendChild(redact);
      }
      elements.evidenceDetails.appendChild(item);
    });
  } catch (err) {
    elements.evidenceDetails.appendChild(
      renderSearchItem("Failed to load evidence.", null)
    );
    console.error(err);
  }
}

function closeEvidencePanel() {
  elements.evidencePanel.classList.add("hidden");
}

function populateRunSelect(runs) {
  clearNode(elements.runSelect);
  if (!runs || runs.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No runs";
    elements.runSelect.appendChild(option);
    return null;
  }
  const current = runs.find((run) => run.is_current);
  const running = runs.find((run) => run.status === "running");
  const completed = runs.find((run) => run.status === "completed");
  const selectedId = current
    ? current.id
    : running
    ? running.id
    : completed
    ? completed.id
    : runs[0].id;
  runs.forEach((run, index) => {
    const option = document.createElement("option");
    option.value = run.id;
    const created = new Date(run.created_at).toLocaleString();
    const label = index === 0 ? "Latest" : "Run";
    const status = run.status || "unknown";
    const currentTag = run.is_current ? " • current" : "";
    option.textContent = `${label} • ${status} • ${created}${currentTag}`;
    elements.runSelect.appendChild(option);
  });
  elements.runSelect.value = selectedId;
  return selectedId;
}

async function loadBundle(sessionId, runId, options = {}) {
  const skipStatusPolling = Boolean(options.skipStatusPolling);
  setStatus("Loading session bundle...");
  const query = runId ? `?run_id=${runId}` : "";
  const bundle = await fetchJson(`/sessions/${sessionId}/bundle${query}`);
  state.bundle = bundle;
  renderBundle(bundle);
  await loadNotesAndBookmarks();
  const runShort = bundle.run_id ? bundle.run_id.slice(0, 8) : "unknown";
  setStatus(`Session loaded. Run ${runShort}.`);
  if (!skipStatusPolling) {
    startRunStatusPolling(sessionId, runId || bundle.run_id);
  }
}

function setUserId(value) {
  const nextValue = value.trim();
  state.currentUserId = nextValue || null;
  if (state.currentUserId) {
    localStorage.setItem("dndUserId", state.currentUserId);
  } else {
    localStorage.removeItem("dndUserId");
  }
}

function renderUserRole() {
  if (!elements.userRole) return;
  if (!state.authEnabled) {
    elements.userRole.textContent = "Auth disabled";
    return;
  }
  if (!state.currentUserId) {
    elements.userRole.textContent = "Set a user id";
    return;
  }
  elements.userRole.textContent = `Role: ${state.userRole || "player"}`;
}

function updateRunControls() {
  if (!elements.startRunButton) return;
  const enabled = canRunSession() && Boolean(state.selectedSession);
  elements.startRunButton.disabled = !enabled;
  if (elements.exportSession) {
    elements.exportSession.disabled = !enabled;
  }
  if (elements.deleteSession) {
    elements.deleteSession.disabled = !enabled;
  }
}

async function loadUserRole() {
  if (!state.selectedCampaign) return;
  try {
    const data = await fetchJson(`/campaigns/${state.selectedCampaign}/me`);
    state.authEnabled = Boolean(data.auth_enabled);
    state.userRole = data.role || "player";
    renderUserRole();
    updateRunControls();
  } catch (err) {
    state.authEnabled = true;
    state.userRole = "player";
    renderUserRole();
    updateRunControls();
    setStatus("Set a user id to continue.");
  }
}

async function refreshAfterCorrection(entityId) {
  await loadCodex();
  if (state.selectedSession && state.selectedRun) {
    await loadBundle(state.selectedSession, state.selectedRun);
  }
  const refreshed = (state.campaignEntities || []).find((entity) => entity.id === entityId);
  if (refreshed) {
    await openEntity(refreshed);
  } else {
    closeEntityPanel();
  }
}

async function applyEntityCorrection(entityId, action, payload, closeOnSuccess = false) {
  setStatus("Saving correction...");
  try {
    await postJson(`/entities/${entityId}/corrections`, {
      action,
      payload,
    });
    setStatus("Correction saved.");
    if (closeOnSuccess) {
      await loadCodex();
      if (state.selectedSession && state.selectedRun) {
        await loadBundle(state.selectedSession, state.selectedRun);
      }
      closeEntityPanel();
      return;
    }
    await refreshAfterCorrection(entityId);
  } catch (err) {
    console.error(err);
    setStatus("Failed to save correction.");
  }
}

function buildEntityEditor(detail) {
  const wrapper = document.createElement("div");
  wrapper.className = "entity-editor";

  const header = document.createElement("div");
  header.className = "editor-header";
  header.innerHTML = "<h4>Corrections</h4><p>Edit names, aliases, or merge/hide entries.</p>";
  wrapper.appendChild(header);

  const renameRow = document.createElement("div");
  renameRow.className = "editor-row";
  const renameLabel = document.createElement("label");
  renameLabel.textContent = "Rename";
  const renameInput = document.createElement("input");
  renameInput.type = "text";
  renameInput.value = detail.name || "";
  renameInput.placeholder = "New canonical name";
  const renameButton = document.createElement("button");
  renameButton.textContent = "Save";
  renameButton.addEventListener("click", async () => {
    const nextName = renameInput.value.trim();
    if (!nextName) return;
    await applyEntityCorrection(detail.id, "entity_rename", { name: nextName });
  });
  renameRow.append(renameLabel, renameInput, renameButton);
  wrapper.appendChild(renameRow);

  const aliasRow = document.createElement("div");
  aliasRow.className = "editor-row";
  const aliasLabel = document.createElement("label");
  aliasLabel.textContent = "Alias";
  const aliasInput = document.createElement("input");
  aliasInput.type = "text";
  aliasInput.placeholder = "Add an alias";
  const aliasButton = document.createElement("button");
  aliasButton.textContent = "Add";
  aliasButton.addEventListener("click", async () => {
    const alias = aliasInput.value.trim();
    if (!alias) return;
    aliasInput.value = "";
    await applyEntityCorrection(detail.id, "entity_alias_add", { alias });
  });
  aliasRow.append(aliasLabel, aliasInput, aliasButton);
  wrapper.appendChild(aliasRow);

  const aliasList = document.createElement("div");
  aliasList.className = "alias-list";
  const aliases = detail.aliases || [];
  if (aliases.length === 0) {
    const empty = document.createElement("span");
    empty.className = "alias-empty";
    empty.textContent = "No aliases yet.";
    aliasList.appendChild(empty);
  } else {
    aliases.forEach((alias) => {
      const chip = document.createElement("div");
      chip.className = "alias-chip";
      const label = document.createElement("span");
      label.textContent = alias;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", async () => {
        await applyEntityCorrection(detail.id, "entity_alias_remove", { alias });
      });
      chip.append(label, remove);
      aliasList.appendChild(chip);
    });
  }
  wrapper.appendChild(aliasList);

  const mergeRow = document.createElement("div");
  mergeRow.className = "editor-row";
  const mergeLabel = document.createElement("label");
  mergeLabel.textContent = "Merge";
  const mergeInput = document.createElement("input");
  mergeInput.type = "text";
  mergeInput.placeholder = "Target entity ID";
  const mergeButton = document.createElement("button");
  mergeButton.textContent = "Merge";
  mergeButton.addEventListener("click", async () => {
    const targetId = mergeInput.value.trim();
    if (!targetId) return;
    if (!confirm("Merge this entity into another? This hides the current entry.")) {
      return;
    }
    await applyEntityCorrection(detail.id, "entity_merge", { into_id: targetId }, true);
  });
  mergeRow.append(mergeLabel, mergeInput, mergeButton);
  wrapper.appendChild(mergeRow);

  const hideRow = document.createElement("div");
  hideRow.className = "editor-row";
  const hideLabel = document.createElement("label");
  hideLabel.textContent = "Hide";
  const hideButton = document.createElement("button");
  hideButton.className = "danger";
  hideButton.textContent = "Hide Entity";
  hideButton.addEventListener("click", async () => {
    if (!confirm("Hide this entity from lists and dashboards?")) {
      return;
    }
    await applyEntityCorrection(detail.id, "entity_hide", {}, true);
  });
  hideRow.append(hideLabel, hideButton);
  wrapper.appendChild(hideRow);

  const spoilerRow = document.createElement("div");
  spoilerRow.className = "editor-row";
  const spoilerLabel = document.createElement("label");
  spoilerLabel.textContent = "Spoiler";
  const spoilerInput = document.createElement("input");
  spoilerInput.type = "number";
  spoilerInput.min = "1";
  spoilerInput.placeholder = "Reveal session #";
  const spoilerButton = document.createElement("button");
  spoilerButton.textContent = "Set";
  spoilerButton.addEventListener("click", async () => {
    const number = Number.parseInt(spoilerInput.value, 10);
    if (!Number.isFinite(number)) return;
    await applySpoiler("entity", detail.id, number);
  });
  spoilerRow.append(spoilerLabel, spoilerInput, spoilerButton);
  wrapper.appendChild(spoilerRow);

  return wrapper;
}

function buildNoteComposer(targetType, targetId, label) {
  const wrapper = document.createElement("div");
  wrapper.className = "note-composer";
  const heading = document.createElement("h4");
  heading.textContent = label || "Notes";
  const textarea = document.createElement("textarea");
  textarea.rows = 3;
  textarea.placeholder = "Add a note...";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Save note";
  button.addEventListener("click", async () => {
    const body = textarea.value.trim();
    if (!body || !state.selectedCampaign) return;
    setStatus("Saving note...");
    try {
      await postJson("/notes", {
        campaign_slug: state.selectedCampaign,
        session_id: state.selectedSession,
        target_type: targetType,
        target_id: targetId,
        body,
      });
      textarea.value = "";
      setStatus("Note saved.");
      if (targetType === "session") {
        await loadNotesAndBookmarks();
      }
    } catch (err) {
      console.error(err);
      setStatus("Failed to save note.");
    }
  });
  wrapper.appendChild(heading);
  wrapper.appendChild(textarea);
  wrapper.appendChild(button);
  return wrapper;
}

async function refreshAfterThreadCorrection(threadId) {
  await loadQuestJournal();
  if (state.selectedSession && state.selectedRun) {
    await loadBundle(state.selectedSession, state.selectedRun);
  }
  const refreshed = (state.questThreads || []).find((thread) => thread.id === threadId);
  if (refreshed) {
    openThread(refreshed);
  } else {
    closeThreadPanel();
  }
}

async function applyThreadCorrection(threadId, action, payload, closeOnSuccess = false) {
  setStatus("Saving correction...");
  try {
    await postJson(`/threads/${threadId}/corrections`, {
      action,
      payload,
    });
    setStatus("Correction saved.");
    if (closeOnSuccess) {
      await loadQuestJournal();
      if (state.selectedSession && state.selectedRun) {
        await loadBundle(state.selectedSession, state.selectedRun);
      }
      closeThreadPanel();
      return;
    }
    await refreshAfterThreadCorrection(threadId);
  } catch (err) {
    console.error(err);
    setStatus("Failed to save correction.");
  }
}

async function applyRedaction(targetType, targetId, label) {
  const message = label ? `Redact ${label}?` : "Redact this item?";
  if (!confirm(message)) {
    return;
  }
  setStatus("Saving redaction...");
  try {
    await postJson("/redactions", {
      target_type: targetType,
      target_id: targetId,
    });
    setStatus("Redaction saved.");
    if (state.selectedSession && state.selectedRun) {
      await loadBundle(state.selectedSession, state.selectedRun);
    }
    closeEvidencePanel();
  } catch (err) {
    console.error(err);
    setStatus("Failed to save redaction.");
  }
}

async function applySpoiler(targetType, targetId, revealNumber) {
  if (!state.selectedCampaign) return;
  let number = revealNumber;
  if (!number) {
    const value = prompt("Hide until session number (e.g. 5)");
    if (!value) return;
    number = Number.parseInt(value, 10);
  }
  if (!Number.isFinite(number) || number < 1) {
    setStatus("Invalid session number.");
    return;
  }
  setStatus("Saving spoiler tag...");
  try {
    await postJson("/spoilers", {
      campaign_slug: state.selectedCampaign,
      target_type: targetType,
      target_id: targetId,
      reveal_session_number: number,
    });
    setStatus("Spoiler tag saved.");
    await loadBundle(state.selectedSession, state.selectedRun);
    await loadQuestJournal();
    await loadCodex();
  } catch (err) {
    console.error(err);
    setStatus("Failed to save spoiler tag.");
  }
}

async function saveBookmark(targetType, targetId) {
  if (!state.selectedCampaign || !state.selectedSession) {
    return;
  }
  setStatus("Saving bookmark...");
  try {
    await postJson("/bookmarks", {
      campaign_slug: state.selectedCampaign,
      session_id: state.selectedSession,
      target_type: targetType,
      target_id: targetId,
    });
    setStatus("Bookmark saved.");
    await loadNotesAndBookmarks();
  } catch (err) {
    console.error(err);
    setStatus("Failed to save bookmark.");
  }
}

function buildThreadEditor(thread) {
  const wrapper = document.createElement("div");
  wrapper.className = "entity-editor";

  const header = document.createElement("div");
  header.className = "editor-header";
  header.innerHTML = "<h4>Quest Controls</h4><p>Update status, title, summary, or merge quests.</p>";
  wrapper.appendChild(header);

  const titleRow = document.createElement("div");
  titleRow.className = "editor-row";
  const titleLabel = document.createElement("label");
  titleLabel.textContent = "Title";
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.value = thread.title || "";
  titleInput.placeholder = "Quest title";
  const titleButton = document.createElement("button");
  titleButton.textContent = "Save";
  titleButton.addEventListener("click", async () => {
    const nextTitle = titleInput.value.trim();
    if (!nextTitle) return;
    await applyThreadCorrection(thread.id, "thread_title", { title: nextTitle });
  });
  titleRow.append(titleLabel, titleInput, titleButton);
  wrapper.appendChild(titleRow);

  const statusRow = document.createElement("div");
  statusRow.className = "editor-row";
  const statusLabel = document.createElement("label");
  statusLabel.textContent = "Status";
  const statusSelect = document.createElement("select");
  ["active", "proposed", "completed", "blocked", "failed", "abandoned"].forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    statusSelect.appendChild(option);
  });
  statusSelect.value = thread.status || "active";
  const statusButton = document.createElement("button");
  statusButton.textContent = "Save";
  statusButton.addEventListener("click", async () => {
    const nextStatus = statusSelect.value;
    await applyThreadCorrection(thread.id, "thread_status", { status: nextStatus });
  });
  statusRow.append(statusLabel, statusSelect, statusButton);
  wrapper.appendChild(statusRow);

  const summaryRow = document.createElement("div");
  summaryRow.className = "editor-row";
  const summaryLabel = document.createElement("label");
  summaryLabel.textContent = "Summary";
  const summaryInput = document.createElement("textarea");
  summaryInput.rows = 4;
  summaryInput.value = thread.summary || "";
  summaryInput.placeholder = "Update quest summary";
  const summaryButton = document.createElement("button");
  summaryButton.textContent = "Save";
  summaryButton.addEventListener("click", async () => {
    await applyThreadCorrection(thread.id, "thread_summary", { summary: summaryInput.value });
  });
  summaryRow.append(summaryLabel, summaryInput, summaryButton);
  wrapper.appendChild(summaryRow);

  const mergeRow = document.createElement("div");
  mergeRow.className = "editor-row";
  const mergeLabel = document.createElement("label");
  mergeLabel.textContent = "Merge";
  const mergeInput = document.createElement("input");
  mergeInput.type = "text";
  mergeInput.placeholder = "Target thread ID";
  const mergeButton = document.createElement("button");
  mergeButton.textContent = "Merge";
  mergeButton.addEventListener("click", async () => {
    const targetId = mergeInput.value.trim();
    if (!targetId) return;
    if (!confirm("Merge this quest into another?")) {
      return;
    }
    await applyThreadCorrection(thread.id, "thread_merge", { into_id: targetId }, true);
  });
  mergeRow.append(mergeLabel, mergeInput, mergeButton);
  wrapper.appendChild(mergeRow);

  const spoilerRow = document.createElement("div");
  spoilerRow.className = "editor-row";
  const spoilerLabel = document.createElement("label");
  spoilerLabel.textContent = "Spoiler";
  const spoilerInput = document.createElement("input");
  spoilerInput.type = "number";
  spoilerInput.min = "1";
  spoilerInput.placeholder = "Reveal session #";
  const spoilerButton = document.createElement("button");
  spoilerButton.textContent = "Set";
  spoilerButton.addEventListener("click", async () => {
    const number = Number.parseInt(spoilerInput.value, 10);
    if (!Number.isFinite(number)) return;
    await applySpoiler("thread", thread.id, number);
  });
  spoilerRow.append(spoilerLabel, spoilerInput, spoilerButton);
  wrapper.appendChild(spoilerRow);

  return wrapper;
}

async function openEntity(entity) {
  if (!entity || !entity.id) return;
  elements.entityTitle.textContent = entity.name;
  elements.entityMeta.textContent = entity.type || "entity";
  clearNode(elements.entityDetails);
  elements.entityPanel.classList.remove("hidden");
  const params = new URLSearchParams();
  if (state.selectedSession) {
    params.set("session_id", state.selectedSession);
  }
  if (state.selectedRun) {
    params.set("run_id", state.selectedRun);
  }
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  try {
    const [detail, mentions, events, quotes] = await Promise.all([
      fetchJson(`/entities/${entity.id}`),
      fetchJson(`/entities/${entity.id}/mentions${suffix}`),
      fetchJson(`/entities/${entity.id}/events${suffix}`),
      fetchJson(`/entities/${entity.id}/quotes${suffix}`),
    ]);
    const canEdit = !state.authEnabled || state.userRole === "dm";
    if (canEdit) {
      elements.entityDetails.appendChild(buildEntityEditor(detail));
    } else {
      elements.entityDetails.appendChild(
        renderSearchItem("Read-only view. DM access required for edits.", null)
      );
    }

    const blocks = [];
    if (mentions.length > 0) {
      blocks.push(
        buildSearchBlock("Mentions", mentions.slice(0, 10), (m) =>
          renderSearchItem(m.text || "mention", sessionLabel(m.session_id) || null)
        )
      );
    }
    if (events.length > 0) {
      blocks.push(
        buildSearchBlock("Events", events.slice(0, 10), (e) =>
          renderSearchItem(e.summary, sessionLabel(e.session_id) || null)
        )
      );
    }
    if (quotes.length > 0) {
      blocks.push(
        buildSearchBlock("Quotes", quotes.slice(0, 10), (q) =>
          renderSearchItem(
            q.display_text || q.clean_text || "",
            [q.speaker, sessionLabel(q.session_id)].filter(Boolean).join(" • ")
          )
        )
      );
    }
    if (blocks.length === 0) {
      elements.entityDetails.appendChild(
        renderSearchItem("No session data for this entity.", null)
      );
    } else {
      blocks.forEach((block) => elements.entityDetails.appendChild(block));
    }
    elements.entityDetails.appendChild(
      buildNoteComposer("entity", detail.id, "Entity notes")
    );
  } catch (err) {
    elements.entityDetails.appendChild(
      renderSearchItem("Failed to load entity dossier.", null)
    );
    console.error(err);
  }
}

function openThread(thread) {
  if (!thread || !thread.id) return;
  elements.threadTitle.textContent = thread.title || "Quest";
  elements.threadMeta.textContent = thread.status || "active";
  clearNode(elements.threadDetails);
  elements.threadPanel.classList.remove("hidden");
  elements.threadDetails.appendChild(buildThreadEditor(thread));
  elements.threadDetails.appendChild(
    buildNoteComposer("thread", thread.id, "Quest notes")
  );
}

function closeEntityPanel() {
  elements.entityPanel.classList.add("hidden");
}

function closeThreadPanel() {
  elements.threadPanel.classList.add("hidden");
}

function buildSearchBlock(title, items, renderFn) {
  const block = document.createElement("div");
  block.className = "search-block";
  const heading = document.createElement("h4");
  heading.textContent = `${title} (${items.length})`;
  block.appendChild(heading);
  items.forEach((item) => block.appendChild(renderFn(item)));
  return block;
}

function renderSearchItem(text, meta, onClick) {
  const item = document.createElement("div");
  item.className = "search-item";
  item.textContent = text;
  if (meta) {
    const small = document.createElement("small");
    small.textContent = meta;
    item.appendChild(small);
  }
  if (onClick) {
    item.style.cursor = "pointer";
    item.addEventListener("click", () => onClick());
  }
  return item;
}

function renderSearchResults(query, data, semantic) {
  clearNode(elements.searchResults);
  elements.searchTitle.textContent = `Results for "${query}"`;
  if (semantic && data.terms) {
    elements.searchSub.textContent = `Expanded terms: ${data.terms.join(", ")}`;
  } else {
    elements.searchSub.textContent = "";
  }

  const blocks = [];
  if (data.mentions && data.mentions.length > 0) {
    blocks.push(
      buildSearchBlock("Mentions", data.mentions, (m) =>
        renderSearchItem(
          `${m.text} (${m.entity_type})`,
          sessionLabel(m.session_id),
          () => jumpToSession(m.session_id)
        )
      )
    );
  }
  if (data.events && data.events.length > 0) {
    blocks.push(
      buildSearchBlock("Events", data.events, (e) =>
        renderSearchItem(e.summary, sessionLabel(e.session_id), () =>
          jumpToSession(e.session_id)
        )
      )
    );
  }
  if (data.threads && data.threads.length > 0) {
    blocks.push(
      buildSearchBlock("Threads", data.threads, (t) =>
        renderSearchItem(t.title, sessionLabel(t.session_id), () =>
          jumpToSession(t.session_id)
        )
      )
    );
  }
  if (data.thread_updates && data.thread_updates.length > 0) {
    blocks.push(
      buildSearchBlock("Thread Updates", data.thread_updates, (u) =>
        renderSearchItem(u.note || "Update", sessionLabel(u.session_id), () =>
          jumpToSession(u.session_id)
        )
      )
    );
  }
  if (data.scenes && data.scenes.length > 0) {
    blocks.push(
      buildSearchBlock("Scenes", data.scenes, (s) =>
        renderSearchItem(s.summary, sessionLabel(s.session_id), () =>
          jumpToSession(s.session_id)
        )
      )
    );
  }
  if (data.quotes && data.quotes.length > 0) {
    blocks.push(
      buildSearchBlock("Quotes", data.quotes, (q) =>
        renderSearchItem(
          q.display_text || q.clean_text || "",
          sessionLabel(q.session_id),
          () => jumpToSession(q.session_id)
        )
      )
    );
  }
  if (data.utterances && data.utterances.length > 0) {
    blocks.push(
      buildSearchBlock("Utterances", data.utterances, (u) =>
        renderSearchItem(u.text, sessionLabel(u.session_id), () =>
          jumpToSession(u.session_id)
        )
      )
    );
  }

  if (blocks.length === 0) {
    elements.searchResults.textContent = "No results returned.";
  } else {
    blocks.forEach((block) => elements.searchResults.appendChild(block));
  }
  elements.searchPanel.classList.remove("hidden");
}

function sessionLabel(sessionId) {
  const session = state.sessionMap[sessionId];
  if (!session) {
    return "";
  }
  const parts = [];
  if (session.session_number != null) {
    parts.push(`Session ${session.session_number}`);
  }
  if (session.title) {
    parts.push(session.title);
  }
  return parts.join(" - ");
}

async function runSearch() {
  const query = elements.searchInput.value.trim();
  if (!query) {
    return;
  }
  if (!state.selectedCampaign) {
    setStatus("Select a campaign before searching.");
    return;
  }
  setStatus("Searching...");
  const semantic = elements.semanticToggle.checked;
  const sessionScope =
    elements.sessionOnlyToggle.checked && state.selectedSession
      ? `&session_id=${encodeURIComponent(state.selectedSession)}`
      : "";
  const endpoint = semantic
    ? `/campaigns/${state.selectedCampaign}/semantic_search?q=${encodeURIComponent(query)}${sessionScope}`
    : `/campaigns/${state.selectedCampaign}/search?q=${encodeURIComponent(query)}${sessionScope}`;
  try {
    const data = await fetchJson(endpoint);
    renderSearchResults(query, data, semantic);
    setStatus("Search complete.");
  } catch (err) {
    setStatus("Search failed.");
    console.error(err);
  }
}

function closeSearch() {
  elements.searchPanel.classList.add("hidden");
}

async function init() {
  const storedUserId = localStorage.getItem("dndUserId") || "";
  if (storedUserId) {
    state.currentUserId = storedUserId;
    if (elements.userIdInput) {
      elements.userIdInput.value = storedUserId;
    }
  }
  renderUserRole();
  elements.campaignSelect.addEventListener("change", async (event) => {
    state.selectedCampaign = event.target.value;
    await loadSessions();
  });
  if (elements.userSetButton && elements.userIdInput) {
    elements.userSetButton.addEventListener("click", async () => {
      setUserId(elements.userIdInput.value || "");
      renderUserRole();
      await loadCampaigns();
    });
    elements.userIdInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        setUserId(elements.userIdInput.value || "");
        renderUserRole();
        await loadCampaigns();
      }
    });
  }
  elements.searchButton.addEventListener("click", runSearch);
  elements.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runSearch();
    }
  });
  if (elements.askButton && elements.askInput) {
    elements.askButton.addEventListener("click", async () => {
      if (!state.selectedCampaign) {
        setStatus("Select a campaign before asking.");
        return;
      }
      const question = elements.askInput.value.trim();
      if (!question) {
        setStatus("Enter a question to ask.");
        return;
      }
      elements.askButton.disabled = true;
      renderAskAnswer("Thinking...");
      renderAskCitations([]);
      setStatus("Asking the campaign...");
      try {
        const response = await askCampaign(question);
        renderAskAnswer(response.answer);
        renderAskCitations(response.citations || []);
        setStatus("Answer ready.");
      } catch (err) {
        console.error(err);
        renderAskAnswer("Failed to get an answer.");
        renderAskCitations([]);
        setStatus("Ask failed.");
      } finally {
        elements.askButton.disabled = false;
      }
    });
    elements.askInput.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        elements.askButton.click();
      }
    });
  }
  elements.closeSearch.addEventListener("click", closeSearch);
  elements.closeEntity.addEventListener("click", closeEntityPanel);
  elements.closeThread.addEventListener("click", closeThreadPanel);
  elements.closeEvidence.addEventListener("click", closeEvidencePanel);
  elements.searchPanel.addEventListener("click", (event) => {
    if (event.target === elements.searchPanel) {
      closeSearch();
    }
  });
  elements.entityPanel.addEventListener("click", (event) => {
    if (event.target === elements.entityPanel) {
      closeEntityPanel();
    }
  });
  elements.threadPanel.addEventListener("click", (event) => {
    if (event.target === elements.threadPanel) {
      closeThreadPanel();
    }
  });
  elements.evidencePanel.addEventListener("click", (event) => {
    if (event.target === elements.evidencePanel) {
      closeEvidencePanel();
    }
  });
  elements.entityFilter.addEventListener("change", () => {
    if (state.bundle) {
      renderEntities(state.bundle.entities || []);
    }
  });
  elements.codexFilter.addEventListener("change", () => {
    renderCodex(state.campaignEntities || []);
  });
  elements.codexSearch.addEventListener("input", () => {
    renderCodex(state.campaignEntities || []);
  });
  elements.questFilter.addEventListener("change", async () => {
    await loadQuestJournal();
  });
  if (elements.saveSessionNote && elements.sessionNote) {
    elements.saveSessionNote.addEventListener("click", async () => {
      if (!state.selectedCampaign || !state.selectedSession) {
        return;
      }
      const body = elements.sessionNote.value.trim();
      if (!body) return;
      setStatus("Saving note...");
      try {
        await postJson("/notes", {
          campaign_slug: state.selectedCampaign,
          session_id: state.selectedSession,
          target_type: "session",
          target_id: state.selectedSession,
          body,
        });
        elements.sessionNote.value = "";
        setStatus("Note saved.");
        await loadNotesAndBookmarks();
      } catch (err) {
        console.error(err);
        setStatus("Failed to save note.");
      }
    });
  }
  if (elements.createSessionButton) {
    elements.createSessionButton.addEventListener("click", async () => {
      await createSessionFromForm();
    });
  }
  if (elements.startRunButton) {
    elements.startRunButton.addEventListener("click", async () => {
      if (!state.selectedSession) {
        setStatus("Select a session before starting a run.");
        return;
      }
      if (!canRunSession()) {
        setStatus("DM access required to start a run.");
        return;
      }
      const session = state.sessionMap[state.selectedSession];
      if (!session) {
        setStatus("Unable to find session.");
        return;
      }
      setStatus("Starting run...");
      try {
        await postJson(
          `/campaigns/${state.selectedCampaign}/sessions/${session.slug}/runs`,
          {}
        );
        const runId = await waitForLatestRun(state.selectedSession, state.selectedRun);
        if (runId) {
          state.selectedRun = runId;
          await setCurrentRun(state.selectedSession, runId);
          await loadSession(state.selectedSession);
        }
        setStatus("Run started.");
      } catch (err) {
        console.error(err);
        setStatus("Failed to start run.");
      }
    });
  }
  elements.runSelect.addEventListener("change", async (event) => {
    const runId = event.target.value;
    state.selectedRun = runId;
    if (state.selectedSession) {
      if (canRunSession() && runId) {
        try {
          await setCurrentRun(state.selectedSession, runId);
        } catch (err) {
          console.error(err);
          setStatus("Failed to set current run.");
        }
      }
      await loadBundle(state.selectedSession, runId);
    }
  });
  if (elements.summaryVariant) {
    elements.summaryVariant.addEventListener("change", (event) => {
      state.summaryVariant = event.target.value;
      renderSummary(state.bundle);
      updateDownload(state.bundle);
    });
  }
  if (elements.summaryFormat) {
    elements.summaryFormat.addEventListener("change", (event) => {
      state.summaryFormat = event.target.value;
      updateDownload(state.bundle);
    });
  }
  if (elements.exportSession) {
    elements.exportSession.addEventListener("click", async () => {
      if (!state.selectedSession) {
        setStatus("Select a session before exporting.");
        return;
      }
      if (!canRunSession()) {
        setStatus("DM access required to export.");
        return;
      }
      setStatus("Exporting session...");
      try {
        await exportSession(state.selectedSession);
        setStatus("Export complete.");
      } catch (err) {
        console.error(err);
        setStatus("Failed to export session.");
      }
    });
  }
  if (elements.deleteSession) {
    elements.deleteSession.addEventListener("click", async () => {
      if (!state.selectedSession) {
        setStatus("Select a session before deleting.");
        return;
      }
      if (!canRunSession()) {
        setStatus("DM access required to delete.");
        return;
      }
      if (!confirm("Delete this session and all derived data?")) {
        return;
      }
      setStatus("Deleting session...");
      try {
        await deleteSession(state.selectedSession);
        state.selectedSession = null;
        state.selectedRun = null;
        renderSessionMeta(null);
        clearNode(elements.runSelect);
        renderRunProgress(null);
        setStatus("Session deleted.");
        await loadSessions();
      } catch (err) {
        console.error(err);
        setStatus("Failed to delete session.");
      }
    });
  }
  elements.downloadSummary.addEventListener("click", () => {
    const mode = elements.downloadSummary.dataset.mode;
    if (!mode || elements.downloadSummary.disabled) {
      return;
    }
    if (mode === "artifact") {
      const href = elements.downloadSummary.dataset.href;
      if (href) {
        window.open(href, "_blank");
      }
      return;
    }
    if (mode === "inline") {
      const text = (state.bundle && state.bundle.summary) || "";
      if (!text) return;
      const blob = new Blob([text], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = elements.downloadSummary.dataset.filename || "summary.txt";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }
  });

  try {
    await loadCampaigns();
  } catch (err) {
    setStatus("Failed to load campaigns.");
    console.error(err);
  }
}

init();
