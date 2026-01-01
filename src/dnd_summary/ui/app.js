const API_BASE = "";

const state = {
  campaigns: [],
  sessions: [],
  sessionMap: {},
  selectedCampaign: null,
  selectedSession: null,
  selectedRun: null,
  bundle: null,
  questThreads: [],
  campaignEntities: [],
  transcriptLines: [],
  utteranceTimecodes: {},
};

const elements = {
  campaignSelect: document.getElementById("campaignSelect"),
  sessionList: document.getElementById("sessionList"),
  sessionCount: document.getElementById("sessionCount"),
  statusLine: document.getElementById("statusLine"),
  sessionMeta: document.getElementById("sessionMeta"),
  runSelect: document.getElementById("runSelect"),
  downloadSummary: document.getElementById("downloadSummary"),
  runMetrics: document.getElementById("runMetrics"),
  summaryText: document.getElementById("summaryText"),
  qualityMetrics: document.getElementById("qualityMetrics"),
  runDiagnostics: document.getElementById("runDiagnostics"),
  artifactLinks: document.getElementById("artifactLinks"),
  threadList: document.getElementById("threadList"),
  sceneList: document.getElementById("sceneList"),
  eventList: document.getElementById("eventList"),
  quoteList: document.getElementById("quoteList"),
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
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
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

function renderArtifacts(artifacts) {
  clearNode(elements.artifactLinks);
  if (!artifacts || artifacts.length === 0) {
    return;
  }
  artifacts.forEach((artifact) => {
    const link = document.createElement("a");
    link.href = `/artifacts/${artifact.id}`;
    link.textContent = `${artifact.kind.replace(/_/g, " ")}`;
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
    if (event.entities && event.entities.length > 0) {
      const row = document.createElement("div");
      row.className = "tag-row";
      event.entities.forEach((entity) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = entity;
        row.appendChild(tag);
      });
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
    elements.eventList.appendChild(card);
  });
}

function renderQuotes(quotes) {
  clearNode(elements.quoteList);
  if (!quotes || quotes.length === 0) {
    elements.quoteList.textContent = "No notable quotes captured.";
    return;
  }
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
  renderMetrics(bundle);
  renderParagraphs(bundle.summary, bundle.run_status);
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
  if (!button) return;
  button.disabled = true;
  button.dataset.mode = "";
  button.dataset.href = "";
  button.dataset.filename = "";

  if (!bundle) {
    button.textContent = "Download Summary";
    return;
  }

  const artifacts = bundle.artifacts || [];
  const docx = artifacts.find((item) => item.kind === "summary_docx");
  const txt = artifacts.find((item) => item.kind === "summary_txt");
  if (docx) {
    button.textContent = "Download DOCX";
    button.dataset.mode = "artifact";
    button.dataset.href = `/artifacts/${docx.id}`;
    button.dataset.filename = "summary.docx";
    button.disabled = false;
    return;
  }
  if (txt) {
    button.textContent = "Download TXT";
    button.dataset.mode = "artifact";
    button.dataset.href = `/artifacts/${txt.id}`;
    button.dataset.filename = "summary.txt";
    button.disabled = false;
    return;
  }
  if (bundle.summary) {
    const session = state.sessionMap[state.selectedSession] || {};
    const slug = session.slug || "summary";
    button.textContent = "Download TXT";
    button.dataset.mode = "inline";
    button.dataset.filename = `${slug}.summary.txt`;
    button.disabled = false;
  } else {
    button.textContent = "Download Summary";
  }
}

async function loadCampaigns() {
  setStatus("Loading campaigns...");
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
  await loadQuestJournal();
  await loadCodex();
  setStatus("Select a session to begin.");
}

async function loadQuestJournal() {
  if (!state.selectedCampaign) return;
  const status = elements.questFilter.value;
  const query = status && status !== "all" ? `?status=${status}` : "";
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
    const entities = await fetchJson(`/campaigns/${state.selectedCampaign}/entities`);
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
  elements.sessionOnlyToggle.disabled = false;
  state.selectedRun = null;
  renderSessions();
  const session = state.sessionMap[sessionId];
  renderSessionMeta(session);
  setStatus("Loading session runs...");
  const runs = await fetchJson(`/sessions/${sessionId}/runs`);
  const activeRun = populateRunSelect(runs);
  state.selectedRun = activeRun;
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
  const completed = runs.find((run) => run.status === "completed");
  const selectedId = completed ? completed.id : runs[0].id;
  runs.forEach((run, index) => {
    const option = document.createElement("option");
    option.value = run.id;
    const created = new Date(run.created_at).toLocaleString();
    const label = index === 0 ? "Latest" : "Run";
    const status = run.status || "unknown";
    option.textContent = `${label} • ${status} • ${created}`;
    elements.runSelect.appendChild(option);
  });
  elements.runSelect.value = selectedId;
  return selectedId;
}

async function loadBundle(sessionId, runId) {
  setStatus("Loading session bundle...");
  const query = runId ? `?run_id=${runId}` : "";
  const bundle = await fetchJson(`/sessions/${sessionId}/bundle${query}`);
  state.bundle = bundle;
  renderBundle(bundle);
  const runShort = bundle.run_id ? bundle.run_id.slice(0, 8) : "unknown";
  setStatus(`Session loaded. Run ${runShort}.`);
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
    elements.entityDetails.appendChild(buildEntityEditor(detail));

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
  } catch (err) {
    elements.entityDetails.appendChild(
      renderSearchItem("Failed to load entity dossier.", null)
    );
    console.error(err);
  }
}

function closeEntityPanel() {
  elements.entityPanel.classList.add("hidden");
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
  elements.campaignSelect.addEventListener("change", async (event) => {
    state.selectedCampaign = event.target.value;
    await loadSessions();
  });
  elements.searchButton.addEventListener("click", runSearch);
  elements.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runSearch();
    }
  });
  elements.closeSearch.addEventListener("click", closeSearch);
  elements.closeEntity.addEventListener("click", closeEntityPanel);
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
  elements.runSelect.addEventListener("change", async (event) => {
    const runId = event.target.value;
    state.selectedRun = runId;
    if (state.selectedSession) {
      await loadBundle(state.selectedSession, runId);
    }
  });
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
