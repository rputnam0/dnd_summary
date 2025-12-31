const API_BASE = "";

const state = {
  campaigns: [],
  sessions: [],
  sessionMap: {},
  selectedCampaign: null,
  selectedSession: null,
  bundle: null,
};

const elements = {
  campaignSelect: document.getElementById("campaignSelect"),
  sessionList: document.getElementById("sessionList"),
  sessionCount: document.getElementById("sessionCount"),
  statusLine: document.getElementById("statusLine"),
  sessionMeta: document.getElementById("sessionMeta"),
  summaryText: document.getElementById("summaryText"),
  artifactLinks: document.getElementById("artifactLinks"),
  threadList: document.getElementById("threadList"),
  sceneList: document.getElementById("sceneList"),
  eventList: document.getElementById("eventList"),
  quoteList: document.getElementById("quoteList"),
  entityList: document.getElementById("entityList"),
  searchInput: document.getElementById("searchInput"),
  searchButton: document.getElementById("searchButton"),
  semanticToggle: document.getElementById("semanticToggle"),
  searchPanel: document.getElementById("searchPanel"),
  searchResults: document.getElementById("searchResults"),
  searchTitle: document.getElementById("searchTitle"),
  searchSub: document.getElementById("searchSub"),
  closeSearch: document.getElementById("closeSearch"),
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

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
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

function renderParagraphs(text) {
  clearNode(elements.summaryText);
  if (!text) {
    elements.summaryText.textContent = "No summary generated yet.";
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
    footer.textContent = `${quote.speaker || "Unknown"} ${quote.note ? "- " + quote.note : ""}`;
    card.appendChild(footer);
    elements.quoteList.appendChild(card);
  });
}

function renderEntities(entities) {
  clearNode(elements.entityList);
  if (!entities || entities.length === 0) {
    elements.entityList.textContent = "No entities in this session.";
    return;
  }
  entities.forEach((entity) => {
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
    elements.entityList.appendChild(card);
  });
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
    card.addEventListener("click", () => loadSession(session.id));
    elements.sessionList.appendChild(card);
  });
}

function renderBundle(bundle) {
  if (!bundle) {
    return;
  }
  renderParagraphs(bundle.summary);
  renderArtifacts(bundle.artifacts || []);
  renderThreads(bundle.threads || []);
  renderScenes(bundle.scenes || []);
  renderEvents(bundle.events || []);
  renderQuotes(bundle.quotes || []);
  renderEntities(bundle.entities || []);
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
  setStatus("Select a session to begin.");
}

async function loadSession(sessionId) {
  if (!sessionId) {
    return;
  }
  state.selectedSession = sessionId;
  renderSessions();
  const session = state.sessionMap[sessionId];
  renderSessionMeta(session);
  setStatus("Loading session bundle...");
  const bundle = await fetchJson(`/sessions/${sessionId}/bundle`);
  state.bundle = bundle;
  renderBundle(bundle);
  setStatus("Session loaded.");
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

function renderSearchItem(text, meta) {
  const item = document.createElement("div");
  item.className = "search-item";
  item.textContent = text;
  if (meta) {
    const small = document.createElement("small");
    small.textContent = meta;
    item.appendChild(small);
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
          sessionLabel(m.session_id)
        )
      )
    );
  }
  if (data.events && data.events.length > 0) {
    blocks.push(
      buildSearchBlock("Events", data.events, (e) =>
        renderSearchItem(e.summary, sessionLabel(e.session_id))
      )
    );
  }
  if (data.threads && data.threads.length > 0) {
    blocks.push(
      buildSearchBlock("Threads", data.threads, (t) =>
        renderSearchItem(t.title, sessionLabel(t.session_id))
      )
    );
  }
  if (data.thread_updates && data.thread_updates.length > 0) {
    blocks.push(
      buildSearchBlock("Thread Updates", data.thread_updates, (u) =>
        renderSearchItem(u.note || "Update", sessionLabel(u.session_id))
      )
    );
  }
  if (data.scenes && data.scenes.length > 0) {
    blocks.push(
      buildSearchBlock("Scenes", data.scenes, (s) =>
        renderSearchItem(s.summary, sessionLabel(s.session_id))
      )
    );
  }
  if (data.quotes && data.quotes.length > 0) {
    blocks.push(
      buildSearchBlock("Quotes", data.quotes, (q) =>
        renderSearchItem(q.display_text || q.clean_text || "", sessionLabel(q.session_id))
      )
    );
  }
  if (data.utterances && data.utterances.length > 0) {
    blocks.push(
      buildSearchBlock("Utterances", data.utterances, (u) =>
        renderSearchItem(u.text, sessionLabel(u.session_id))
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
  const endpoint = semantic
    ? `/campaigns/${state.selectedCampaign}/semantic_search?q=${encodeURIComponent(query)}`
    : `/campaigns/${state.selectedCampaign}/search?q=${encodeURIComponent(query)}`;
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
  elements.searchPanel.addEventListener("click", (event) => {
    if (event.target === elements.searchPanel) {
      closeSearch();
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
