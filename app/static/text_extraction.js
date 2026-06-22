const textForm = document.querySelector("#textJobForm");
const createTextJobsButton = document.querySelector("#createTextJobsButton");
const spreadsheetInput = document.querySelector("#spreadsheetInput");
const chooseSpreadsheetButton = document.querySelector("#chooseSpreadsheetButton");
const spreadsheetInputSummary = document.querySelector("#spreadsheetInputSummary");
const columnMappings = document.querySelector("#columnMappings");
const addMappingButton = document.querySelector("#addMappingButton");
const studyIdColumnInput = document.querySelector("#studyIdColumnInput");
const modelPresetSelect = document.querySelector("#modelPresetSelect");
const openaiApiKeyField = document.querySelector("#openaiApiKeyField");
const promptTemplateInput = document.querySelector("#promptTemplateInput");
const promptFilenameInput = document.querySelector("#promptFilenameInput");
const rqSystemPromptInput = document.querySelector("#rqSystemPromptInput");
const savePromptButton = document.querySelector("#savePromptButton");
const loadSavedPromptButton = document.querySelector("#loadSavedPromptButton");
const promptStatus = document.querySelector("#promptStatus");
const textQueueBadge = document.querySelector("#textQueueBadge");
const textStatusLine = document.querySelector("#textStatusLine");
const textCounts = document.querySelector("#textCounts");
const pauseTextQueueButton = document.querySelector("#pauseTextQueueButton");
const resumeTextQueueButton = document.querySelector("#resumeTextQueueButton");
const retryFailedRowsButton = document.querySelector("#retryFailedRowsButton");
const textExportLink = document.querySelector("#textExportLink");
const textStatusFilterButtons = [...document.querySelectorAll("[data-text-status-filter]")];
const textSearchInput = document.querySelector("#textSearchInput");
const clearTextSearchButton = document.querySelector("#clearTextSearchButton");
const textFilterSummaryLine = document.querySelector("#textFilterSummaryLine");
const textTableHeader = document.querySelector(".text-table-header");
const textTableViewport = document.querySelector("#textTableViewport");
const textVirtualSpacer = document.querySelector("#textVirtualSpacer");
const textVirtualRows = document.querySelector("#textVirtualRows");
const currentProjectId = document.body.dataset.currentProjectId || document.querySelector("#currentProjectId")?.value || "";
const currentProjectName = document.body.dataset.currentProjectName || "";
const projectSidebar = document.querySelector("#projectSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const projectsNavItem = document.querySelector("#projectsNavItem");
const projectsMenuButton = document.querySelector("#projectsMenuButton");
const projectsFlyout = document.querySelector("#projectsFlyout");
const currentProjectNameLabel = document.querySelector("#currentProjectName");
const initialProjects = JSON.parse(document.querySelector("#projectData")?.textContent || "[]");
const modelPresets = JSON.parse(document.querySelector("#modelPresetData")?.textContent || "[]");

const ROW_HEIGHT = 64;
const WINDOW_LIMIT = 120;
const SCROLL_OVERSCAN = 12;

let activeStatusFilter = "all";
let textSearchQuery = "";
let totalRows = 0;
let loadedWindow = { offset: -1, limit: 0, items: [], status: "", search: "" };
let windowRequestKey = "";
let countsTimer = null;
let visibleWindowTimer = null;
let searchDebounceTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  initializeProjectSidebar();
  renderProjectChoices(initialProjects);
  loadProjectList();
  updateProjectLinks();
  renderSelectedModelPreset();
  addMappingRow();
  updateSpreadsheetSummary();
  loadPromptTemplate();
  refreshCounts();
  loadVisibleWindow(0, { force: true });
  startPolling();
});

chooseSpreadsheetButton.addEventListener("click", () => spreadsheetInput.click());
spreadsheetInput.addEventListener("change", updateSpreadsheetSummary);
modelPresetSelect.addEventListener("change", renderSelectedModelPreset);
addMappingButton.addEventListener("click", () => addMappingRow());
savePromptButton.addEventListener("click", savePromptTemplate);
loadSavedPromptButton.addEventListener("click", showSavedPromptPicker);

textForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = spreadsheetInput.files[0];
  if (!file) {
    setTextStatus("Choose a CSV or XLSX file.", "failed");
    return;
  }
  const mappings = collectMappings();
  if (!mappings.length) {
    setTextStatus("Add at least one column mapping.", "failed");
    return;
  }
  createTextJobsButton.disabled = true;
  try {
    setTextStatus("Creating row jobs...", "running");
    const body = buildTextJobFormData(file, mappings);
    const response = await fetch("/api/text/jobs", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to create row jobs.");
    }
    setTextStatus(`Queued ${payload.count || 0} row job${payload.count === 1 ? "" : "s"}.`, "queued");
    spreadsheetInput.value = "";
    updateSpreadsheetSummary();
    textTableViewport.scrollTop = 0;
    await refreshCounts();
    await loadVisibleWindow(0, { force: true });
  } catch (error) {
    setTextStatus(error.message || "Failed to create row jobs.", "failed");
  } finally {
    createTextJobsButton.disabled = false;
  }
});

for (const button of textStatusFilterButtons) {
  button.addEventListener("click", async () => {
    activeStatusFilter = button.dataset.textStatusFilter || "all";
    textTableViewport.scrollTop = 0;
    renderFilterButtons();
    await loadVisibleWindow(0, { force: true });
  });
}

textSearchInput.addEventListener("input", () => {
  window.clearTimeout(searchDebounceTimer);
  searchDebounceTimer = window.setTimeout(async () => {
    textSearchQuery = textSearchInput.value || "";
    textTableViewport.scrollTop = 0;
    await loadVisibleWindow(0, { force: true });
  }, 250);
});

clearTextSearchButton.addEventListener("click", async () => {
  textSearchQuery = "";
  textSearchInput.value = "";
  textTableViewport.scrollTop = 0;
  await loadVisibleWindow(0, { force: true });
  textSearchInput.focus();
});

pauseTextQueueButton.addEventListener("click", async () => {
  pauseTextQueueButton.disabled = true;
  try {
    const response = await fetch("/api/text/queue/pause", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not pause text queue.");
    setTextStatus("Text queue paused. Active rows will finish.", "queued");
    await refreshCounts();
  } catch (error) {
    setTextStatus(error.message || "Could not pause text queue.", "failed");
  } finally {
    pauseTextQueueButton.disabled = false;
  }
});

resumeTextQueueButton.addEventListener("click", async () => {
  resumeTextQueueButton.disabled = true;
  try {
    const response = await fetch("/api/text/queue/resume", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not resume text queue.");
    setTextStatus("Text queue resumed.", "running");
    await refreshCounts();
  } catch (error) {
    setTextStatus(error.message || "Could not resume text queue.", "failed");
  } finally {
    resumeTextQueueButton.disabled = false;
  }
});

textTableViewport.addEventListener("scroll", () => {
  if (textTableHeader) {
    textTableHeader.style.transform = `translateX(${-textTableViewport.scrollLeft}px)`;
  }
  window.requestAnimationFrame(() => {
    const offset = Math.max(0, Math.floor(textTableViewport.scrollTop / ROW_HEIGHT) - SCROLL_OVERSCAN);
    loadVisibleWindow(offset);
  });
});

retryFailedRowsButton.addEventListener("click", async () => {
  retryFailedRowsButton.disabled = true;
  try {
    const response = await fetch("/api/text/jobs/retry-failed", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Could not retry failed rows.");
    }
    const skipped = payload.skipped?.length || 0;
    setTextStatus(
      `Retried ${payload.requeued || 0} failed row${payload.requeued === 1 ? "" : "s"}.${skipped ? ` ${skipped} skipped.` : ""}`,
      skipped ? "failed" : "queued"
    );
    await refreshCounts();
    await refreshVisibleWindow();
  } catch (error) {
    setTextStatus(error.message || "Could not retry failed rows.", "failed");
  } finally {
    retryFailedRowsButton.disabled = false;
  }
});

function initializeProjectSidebar() {
  if (currentProjectNameLabel && currentProjectName) {
    currentProjectNameLabel.textContent = currentProjectName;
  }
  if (sidebarToggle && projectSidebar) {
    sidebarToggle.addEventListener("click", () => {
      const isCollapsed = projectSidebar.classList.toggle("collapsed");
      sidebarToggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    });
  }
  if (projectsMenuButton && projectSidebar) {
    projectsMenuButton.addEventListener("click", () => {
      const isOpen = projectSidebar.classList.toggle("projects-open");
      projectsMenuButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
  }
  if (projectsNavItem && projectSidebar) {
    projectsNavItem.addEventListener("mouseenter", () => {
      projectSidebar.classList.add("projects-hover");
      projectsMenuButton?.setAttribute("aria-expanded", "true");
    });
    projectsNavItem.addEventListener("mouseleave", () => {
      projectSidebar.classList.remove("projects-hover");
      if (!projectSidebar.classList.contains("projects-open")) {
        projectsMenuButton?.setAttribute("aria-expanded", "false");
      }
    });
  }
}

async function loadProjectList() {
  if (!projectsFlyout) return;
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) return;
    const payload = await response.json();
    renderProjectChoices(payload.projects || []);
  } catch (_error) {
    return;
  }
}

function renderProjectChoices(projects) {
  if (!projectsFlyout) return;
  const items = (projects || [])
    .map((project) => {
      const projectId = project.project_id || "";
      const active = projectId === currentProjectId ? "active" : "";
      const extractionType = project.extraction_type || "pdf";
      const label =
        project.extraction_type_label ||
        (extractionType === "text"
          ? "Text extraction"
          : extractionType === "pdf_structured"
            ? "Structured PDF extraction"
            : "PDF extraction");
      const dashboardPath =
        project.dashboard_path ||
        (extractionType === "text"
          ? `/text?project_id=${encodeURIComponent(projectId)}`
          : extractionType === "pdf_structured"
            ? `/structured-pdf?project_id=${encodeURIComponent(projectId)}`
            : `/rq-screening?project_id=${encodeURIComponent(projectId)}`);
      return `
        <button type="button" class="project-choice ${active}" data-project-id="${escapeHtml(projectId)}" data-dashboard-path="${escapeHtml(dashboardPath)}" role="menuitem">
          <strong>${escapeHtml(project.name || projectId)}</strong>
          <small>${escapeHtml(label)}</small>
        </button>
      `;
    })
    .join("");
  projectsFlyout.innerHTML = items || `<p class="technical-empty">No projects found.</p>`;
  projectsFlyout.querySelectorAll("[data-project-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextProjectId = button.dataset.projectId || "";
      if (!nextProjectId || nextProjectId === currentProjectId) return;
      window.location.href = button.dataset.dashboardPath || `/?project_id=${encodeURIComponent(nextProjectId)}`;
    });
  });
}

function updateProjectLinks() {
  if (textExportLink) {
    textExportLink.href = withProject("/api/text/export");
  }
}

function withProject(url) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}project_id=${encodeURIComponent(currentProjectId)}`;
}

function buildProjectFormData() {
  const body = new FormData();
  body.append("project_id", currentProjectId);
  return body;
}

function buildTextJobFormData(file, mappings) {
  syncSystemPromptField();
  const body = new FormData();
  body.append("project_id", currentProjectId);
  body.append("spreadsheet", file, file.name);
  body.append("column_mappings", JSON.stringify(mappings));
  body.append("study_id_column", studyIdColumnInput.value || "");
  body.append("rq_model_preset", modelPresetSelect.value || "");
  body.append("openai_api_key", textForm.querySelector("[name='openai_api_key']")?.value || "");
  body.append("rq_prompt_filename", promptFilenameInput.value || "");
  body.append("rq_system_prompt", rqSystemPromptInput.value || "");
  return body;
}

function renderSelectedModelPreset() {
  const preset = selectedPreset();
  const settings = preset?.settings || {};
  const isOpenAI = settings.provider === "openai";
  openaiApiKeyField.classList.toggle("hidden", !isOpenAI);
}

function selectedPreset() {
  return modelPresets.find((preset) => preset.id === modelPresetSelect.value) || modelPresets[0] || null;
}

function addMappingRow(columnName = "", promptLabel = "") {
  const row = document.createElement("div");
  row.className = "column-mapping-row";
  row.innerHTML = `
    <label class="field">
      <span>Column name</span>
      <input data-mapping-field="column_name" type="text" value="${escapeAttribute(columnName)}" placeholder="abstract" />
    </label>
    <label class="field">
      <span>Prompt label</span>
      <input data-mapping-field="prompt_label" type="text" value="${escapeAttribute(promptLabel)}" placeholder="Abstract" />
    </label>
    <button class="icon-button remove-mapping-button" type="button" aria-label="Remove column mapping" title="Remove column mapping">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18"></path>
      </svg>
    </button>
  `;
  row.querySelector(".remove-mapping-button").addEventListener("click", () => {
    if (columnMappings.querySelectorAll(".column-mapping-row").length <= 1) {
      row.querySelector("[data-mapping-field='column_name']").value = "";
      row.querySelector("[data-mapping-field='prompt_label']").value = "";
      return;
    }
    row.remove();
  });
  columnMappings.appendChild(row);
}

function collectMappings() {
  const mappings = [];
  for (const row of columnMappings.querySelectorAll(".column-mapping-row")) {
    const columnName = row.querySelector("[data-mapping-field='column_name']")?.value.trim() || "";
    const promptLabel = row.querySelector("[data-mapping-field='prompt_label']")?.value.trim() || "";
    if (!columnName && !promptLabel) continue;
    mappings.push({ column_name: columnName, prompt_label: promptLabel });
  }
  return mappings;
}

function updateSpreadsheetSummary() {
  const file = spreadsheetInput.files[0];
  if (!file) {
    spreadsheetInputSummary.textContent = "No file selected";
    return;
  }
  spreadsheetInputSummary.textContent = `${file.name} (${formatBytes(file.size)})`;
}

async function loadPromptTemplate(filename = "Animal_studies_1.txt") {
  loadSavedPromptButton.disabled = true;
  setPromptStatus("Loading prompt...", "");
  try {
    const response = await fetch(`/api/rq-prompts/${encodeURIComponent(filename)}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to load prompt.");
    }
    const prompt = payload.prompt || {};
    promptTemplateInput.value = prompt.system_prompt || "";
    promptFilenameInput.value = prompt.filename || filename;
    syncSystemPromptField();
    setPromptStatus(`Loaded ${prompt.filename || filename}.`, "complete");
  } catch (error) {
    setPromptStatus(error.message || "Failed to load prompt.", "failed");
  } finally {
    loadSavedPromptButton.disabled = false;
  }
}

async function savePromptTemplate() {
  savePromptButton.disabled = true;
  setPromptStatus("Saving prompt...", "");
  try {
    const body = new FormData();
    body.append("filename", promptFilenameInput.value || "");
    body.append("system_prompt", promptTemplateInput.value || "");
    const response = await fetch("/api/rq-prompt", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to save prompt.");
    }
    const prompt = payload.prompt || {};
    promptTemplateInput.value = prompt.system_prompt || "";
    promptFilenameInput.value = prompt.filename || promptFilenameInput.value;
    syncSystemPromptField();
    setPromptStatus(`Saved ${prompt.filename}.`, "complete");
  } catch (error) {
    setPromptStatus(error.message || "Failed to save prompt.", "failed");
  } finally {
    savePromptButton.disabled = false;
  }
}

async function showSavedPromptPicker() {
  loadSavedPromptButton.disabled = true;
  try {
    const response = await fetch("/api/rq-prompts");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Failed to load saved prompts.");
    }
    renderPromptPicker(payload.prompts || []);
  } catch (error) {
    setPromptStatus(error.message || "Failed to load saved prompts.", "failed");
  } finally {
    loadSavedPromptButton.disabled = false;
  }
}

function renderPromptPicker(prompts) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  const items = prompts
    .map((prompt) => `<button type="button" class="prompt-choice" data-filename="${escapeHtml(prompt.filename)}">${escapeHtml(prompt.filename)}</button>`)
    .join("");
  overlay.innerHTML = `
    <div class="modal">
      <p>Load saved prompt</p>
      <div class="prompt-choice-list">${items || "<p>No prompt files found.</p>"}</div>
      <div class="modal-actions">
        <button type="button" data-action="cancel">Cancel</button>
      </div>
    </div>
  `;
  overlay.querySelector("[data-action='cancel']").addEventListener("click", () => overlay.remove());
  overlay.querySelectorAll(".prompt-choice").forEach((button) => {
    button.addEventListener("click", async () => {
      const filename = button.dataset.filename;
      overlay.remove();
      await loadPromptTemplate(filename);
    });
  });
  document.body.appendChild(overlay);
}

function syncSystemPromptField() {
  rqSystemPromptInput.value = promptTemplateInput.value || "";
}

function setPromptStatus(message, status) {
  promptStatus.textContent = message;
  promptStatus.className = `prompt-status ${status || ""}`;
}

function startPolling() {
  if (!countsTimer) countsTimer = window.setInterval(refreshCounts, 2500);
  if (!visibleWindowTimer) visibleWindowTimer = window.setInterval(refreshVisibleWindow, 3000);
}

async function refreshCounts() {
  try {
    const response = await fetch(withProject("/api/text/jobs/counts"));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) return;
    renderCounts(payload.counts || {}, payload.queue || {});
  } catch (_error) {
    return;
  }
}

function renderCounts(counts, queue) {
  const normalized = {
    total: Number(counts.total || 0),
    queued: Number(counts.queued || 0),
    running: Number(counts.running || 0),
    completed: Number(counts.completed || 0),
    failed: Number(counts.failed || 0),
  };
  const metrics = [
    { label: "Total rows", value: normalized.total, tone: "" },
    { label: "Completed", value: normalized.completed, tone: "complete" },
    { label: "Running", value: normalized.running, tone: "running" },
    { label: "Queued", value: normalized.queued, tone: "queued" },
    { label: "Failed", value: normalized.failed, tone: "failed" },
    {
      label: "Workers",
      value: Number(queue.running_count || 0),
      detail: `${Number(queue.pending_count || 0)} pending | ${Number(queue.max_text_workers || 0)} max`,
      tone: "workers",
    },
  ];
  textCounts.innerHTML = metrics
    .map(
      (metric) => `
        <div class="stat-card ${metric.tone}">
          <span>${escapeHtml(metric.label)}</span>
          <strong>${escapeHtml(metric.value)}</strong>
          ${metric.detail ? `<small>${escapeHtml(metric.detail)}</small>` : ""}
        </div>
      `
    )
    .join("");
  textQueueBadge.textContent = normalized.total ? `${normalized.completed} / ${normalized.total} complete` : "No rows";
  textQueueBadge.className = `badge ${normalized.failed ? "failed" : normalized.running ? "running" : normalized.queued ? "queued" : normalized.completed ? "complete" : ""}`;
  if (!normalized.total) {
    textStatusLine.textContent = "No rows are currently being tracked.";
  } else {
    const queueState = queue.paused ? "Text queue paused. " : "";
    textStatusLine.textContent = `${queueState}${normalized.completed} of ${normalized.total} rows completed. ${normalized.running} running, ${normalized.queued} queued.${normalized.failed ? ` ${normalized.failed} failed.` : ""}`;
  }
  pauseTextQueueButton.disabled = Boolean(queue.paused);
  resumeTextQueueButton.disabled = !queue.paused;
  updateFilterCounts(normalized);
}

function updateFilterCounts(counts) {
  const values = {
    all: counts.total || 0,
    queued: counts.queued || 0,
    running: counts.running || 0,
    completed: counts.completed || 0,
    failed: counts.failed || 0,
  };
  for (const item of document.querySelectorAll("[data-text-count]")) {
    const key = item.dataset.textCount || "all";
    item.textContent = values[key] ?? 0;
  }
}

async function refreshVisibleWindow() {
  const offset = loadedWindow.offset >= 0 ? loadedWindow.offset : visibleOffset();
  await loadVisibleWindow(offset, { force: true, quiet: true });
}

async function loadVisibleWindow(offset = visibleOffset(), options = {}) {
  const safeOffset = Math.max(0, offset);
  const key = `${safeOffset}:${activeStatusFilter}:${textSearchQuery}`;
  if (!options.force && key === windowRequestKey) return;
  if (!options.force && loadedWindow.offset <= safeOffset && safeOffset < loadedWindow.offset + Math.max(1, loadedWindow.limit - 40)) {
    return;
  }
  windowRequestKey = key;
  try {
    const params = new URLSearchParams({
      project_id: currentProjectId,
      offset: String(safeOffset),
      limit: String(WINDOW_LIMIT),
      status: activeStatusFilter,
      search: textSearchQuery,
    });
    const response = await fetch(`/api/text/jobs?${params.toString()}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (!options.quiet) setTextStatus(payload.detail || "Could not load rows.", "failed");
      return;
    }
    totalRows = Number(payload.total || 0);
    loadedWindow = {
      offset: Number(payload.offset || 0),
      limit: Number(payload.limit || WINDOW_LIMIT),
      items: payload.items || [],
      status: activeStatusFilter,
      search: textSearchQuery,
    };
    renderVirtualRows();
    renderFilterButtons();
  } catch (_error) {
    if (!options.quiet) setTextStatus("Could not load rows.", "failed");
  }
}

function visibleOffset() {
  return Math.max(0, Math.floor(textTableViewport.scrollTop / ROW_HEIGHT) - SCROLL_OVERSCAN);
}

function renderVirtualRows() {
  textVirtualSpacer.style.height = `${Math.max(1, totalRows) * ROW_HEIGHT}px`;
  if (!totalRows) {
    textVirtualRows.innerHTML = `
      <div class="text-table-empty">
        <strong>No rows match the current filters.</strong>
        <span>Upload a spreadsheet or adjust the filters.</span>
      </div>
    `;
    textVirtualSpacer.style.height = "160px";
    renderFilterSummary(0);
    return;
  }
  textVirtualRows.innerHTML = "";
  loadedWindow.items.forEach((item, index) => {
    const rowIndex = loadedWindow.offset + index;
    const row = document.createElement("div");
    row.className = `text-table-row text-table-grid ${statusClass(item.status)}`;
    row.style.transform = `translateY(${rowIndex * ROW_HEIGHT}px)`;
    row.innerHTML = `
      <span class="row-number">${escapeHtml(item.row || rowIndex + 1)}</span>
      <span><span class="status-badge ${statusClass(item.status)}">${escapeHtml(item.status_label || item.status)}</span></span>
      <span class="truncate-cell" title="${escapeAttribute(item.record_id || "")}">${escapeHtml(item.record_id || "")}</span>
      <span class="truncate-cell" title="${escapeAttribute(item.input_preview || "")}">${escapeHtml(item.input_preview || "")}</span>
      <span class="truncate-cell" title="${escapeAttribute(item.model || "")}">${escapeHtml(item.model || "")}</span>
      <span class="truncate-cell" title="${escapeAttribute(item.prompt || "")}">${escapeHtml(item.prompt || "")}</span>
      <span class="truncate-cell">${escapeHtml(jobTimeText(item))}</span>
      <span>${escapeHtml(formatDurationValue(item.duration_seconds))}</span>
      <span class="truncate-cell" title="${escapeAttribute(item.result_preview || item.error || "")}">${escapeHtml(item.result_preview || item.error || "")}</span>
      <span class="text-row-actions">
        <button type="button" data-action="view">View</button>
        <button type="button" data-action="retry" ${item.status === "failed" ? "" : "disabled"}>Retry</button>
      </span>
    `;
    row.querySelector("[data-action='view']").addEventListener("click", () => showRowOutput(item.job_id));
    row.querySelector("[data-action='retry']").addEventListener("click", () => retryRow(item.job_id));
    textVirtualRows.appendChild(row);
  });
  renderFilterSummary(totalRows);
}

function renderFilterButtons() {
  for (const button of textStatusFilterButtons) {
    const active = button.dataset.textStatusFilter === activeStatusFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }
  clearTextSearchButton.disabled = !textSearchQuery.trim();
}

function renderFilterSummary(visibleTotal) {
  const searchText = textSearchQuery.trim() ? ` matching "${textSearchQuery.trim()}"` : "";
  const filterText = activeStatusFilter === "all" ? "all rows" : `${activeStatusFilter} rows`;
  textFilterSummaryLine.textContent = `Showing ${visibleTotal} ${filterText}${searchText}.`;
}

async function showRowOutput(jobId) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal text-output-modal">
      <p>Row output</p>
      <pre>Loading...</pre>
      <div class="modal-actions">
        <button type="button" data-action="close">Close</button>
      </div>
    </div>
  `;
  overlay.querySelector("[data-action='close']").addEventListener("click", () => overlay.remove());
  document.body.appendChild(overlay);
  try {
    const response = await fetch(withProject(`/api/text/jobs/${encodeURIComponent(jobId)}/output`));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Could not load row output.");
    }
    const metadata = payload.metadata || {};
    overlay.querySelector(".modal").innerHTML = `
      <p>${escapeHtml(metadata.record_id || jobId)}</p>
      <div class="text-output-tabs">
        <details open>
          <summary>Output</summary>
          <pre>${escapeHtml(payload.output || "No output yet.")}</pre>
        </details>
        <details>
          <summary>User prompt</summary>
          <pre>${escapeHtml(payload.user_prompt || "")}</pre>
        </details>
        <details>
          <summary>System prompt</summary>
          <pre>${escapeHtml(payload.system_prompt || "")}</pre>
        </details>
        <details>
          <summary>Metadata</summary>
          <pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre>
        </details>
      </div>
      <div class="modal-actions">
        <button type="button" data-action="close">Close</button>
      </div>
    `;
    overlay.querySelector("[data-action='close']").addEventListener("click", () => overlay.remove());
  } catch (error) {
    overlay.querySelector("pre").textContent = error.message || "Could not load row output.";
  }
}

async function retryRow(jobId) {
  try {
    const response = await fetch(`/api/text/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Could not retry row.");
    }
    setTextStatus("Row queued with its original saved settings.", "queued");
    await refreshCounts();
    await refreshVisibleWindow();
  } catch (error) {
    setTextStatus(error.message || "Could not retry row.", "failed");
  }
}

function setTextStatus(message, tone) {
  textStatusLine.textContent = message;
  textQueueBadge.className = `badge ${tone || ""}`;
  if (tone === "failed") textQueueBadge.textContent = "Attention";
  if (tone === "running") textQueueBadge.textContent = "Working";
  if (tone === "queued") textQueueBadge.textContent = "Queued";
}

function jobTimeText(item) {
  if (item.completed_at) return `Completed ${formatDate(item.completed_at)}`;
  if (item.started_at) return `Started ${formatDate(item.started_at)}`;
  return item.stage || "";
}

function formatDurationValue(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "");
  return date.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function formatBytes(size) {
  const bytes = Number(size || 0);
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function statusClass(status) {
  if (status === "completed" || status === "complete") return "complete";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  return "queued";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
