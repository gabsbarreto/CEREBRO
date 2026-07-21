const currentProjectId = document.body.dataset.currentProjectId || document.querySelector("#currentProjectId")?.value || "";
const currentProjectName = document.body.dataset.currentProjectName || "";
const initialProjects = JSON.parse(document.querySelector("#projectData")?.textContent || "[]");
const modelPresets = JSON.parse(document.querySelector("#modelPresetData")?.textContent || "[]");

const sourceSetupPanel = document.querySelector("#sourceSetupPanel");
const sourceSummaryPanel = document.querySelector("#sourceSummaryPanel");
const textWorkbookPanel = document.querySelector("#textWorkbookPanel");
const textSourceForm = document.querySelector("#textSourceForm");
const createTextWorkbookButton = document.querySelector("#createTextWorkbookButton");
const spreadsheetInput = document.querySelector("#spreadsheetInput");
const chooseSpreadsheetButton = document.querySelector("#chooseSpreadsheetButton");
const spreadsheetInputSummary = document.querySelector("#spreadsheetInputSummary");
const columnMappings = document.querySelector("#columnMappings");
const addMappingButton = document.querySelector("#addMappingButton");
const studyIdColumnInput = document.querySelector("#studyIdColumnInput");
const sourceFilenameLabel = document.querySelector("#sourceFilenameLabel");
const sourceDetailsLabel = document.querySelector("#sourceDetailsLabel");
const frozenMappingList = document.querySelector("#frozenMappingList");
const spreadsheetPreviewPanel = document.querySelector("#spreadsheetPreviewPanel");
const spreadsheetInspectionSummary = document.querySelector("#spreadsheetInspectionSummary");
const spreadsheetPreviewTable = document.querySelector("#spreadsheetPreviewTable");
const sourceInspectionStatus = document.querySelector("#sourceInspectionStatus");

const textSheetTabs = document.querySelector("#textSheetTabs");
const textSheetTabsScrollLeft = document.querySelector("#textSheetTabsScrollLeft");
const textSheetTabsScrollRight = document.querySelector("#textSheetTabsScrollRight");
const addTextSheetButton = document.querySelector("#addTextSheetButton");
const duplicateTextSheetButton = document.querySelector("#duplicateTextSheetButton");
const textSheetForm = document.querySelector("#textSheetForm");
const textSheetNameInput = document.querySelector("#textSheetNameInput");
const textSheetLockNotice = document.querySelector("#textSheetLockNotice");
const textSheetSaveStatus = document.querySelector("#textSheetSaveStatus");
const runTextSheetButton = document.querySelector("#runTextSheetButton");
const modelPresetSelect = document.querySelector("#modelPresetSelect");
const openaiApiKeyField = document.querySelector("#openaiApiKeyField");
const promptTemplateInput = document.querySelector("#promptTemplateInput");
const promptFilenameInput = document.querySelector("#promptFilenameInput");
const savePromptButton = document.querySelector("#savePromptButton");
const loadSavedPromptButton = document.querySelector("#loadSavedPromptButton");
const promptStatus = document.querySelector("#promptStatus");
const toggleTextSheetSetupButton = document.querySelector("#toggleTextSheetSetupButton");
const textSheetSetupBody = document.querySelector("#textSheetSetupBody");
const textSheetProvenanceSummary = document.querySelector("#textSheetProvenanceSummary");

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
const textWorkbookHeader = document.querySelector("#textWorkbookHeader");
const textWorkbookTableShell = document.querySelector("#textWorkbookTableShell");
const textTableViewport = document.querySelector("#textTableViewport");
const textVirtualSpacer = document.querySelector("#textVirtualSpacer");
const textVirtualRows = document.querySelector("#textVirtualRows");

const projectSidebar = document.querySelector("#projectSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const projectsNavItem = document.querySelector("#projectsNavItem");
const projectsMenuButton = document.querySelector("#projectsMenuButton");
const projectsFlyout = document.querySelector("#projectsFlyout");
const currentProjectNameLabel = document.querySelector("#currentProjectName");

const ROW_HEIGHT = 42;
const WINDOW_LIMIT = 120;
const SCROLL_OVERSCAN = 12;

let workbookState = { source: null, sheets: [] };
let activeSheetId = "";
let activeStatusFilter = "all";
let textSearchQuery = "";
let totalRows = 0;
let loadedWindow = { offset: -1, limit: 0, items: [] };
let windowRequestKey = "";
let textPollingTimer = null;
let lastTextCounts = { total: 0, not_run: 0, queued: 0, running: 0, completed: 0, failed: 0 };
let searchDebounceTimer = null;
let autosaveTimer = null;
let sheetDirty = false;
let sheetSaveInFlight = false;
let inspectedColumns = [];
let inspectedPreviewRows = [];

document.addEventListener("DOMContentLoaded", async () => {
  initializeProjectSidebar();
  renderProjectChoices(initialProjects);
  loadProjectList();
  updateProjectLinks();
  addMappingRow();
  updateSpreadsheetSummary();
  renderSelectedModelPreset();
  await loadWorkbook();
  startPolling();
});

chooseSpreadsheetButton.addEventListener("click", () => spreadsheetInput.click());
spreadsheetInput.addEventListener("change", inspectSelectedSpreadsheet);
addMappingButton.addEventListener("click", () => addMappingRow());
toggleTextSheetSetupButton?.addEventListener("click", () => {
  setTextSheetSetupCollapsed(!textSheetSetupBody.classList.contains("hidden"));
});
document.addEventListener("visibilitychange", () => {
  scheduleTextPolling(document.hidden ? 30000 : 0);
});
modelPresetSelect.addEventListener("change", () => {
  renderSelectedModelPreset();
  markSheetDirty();
});
textSheetNameInput.addEventListener("input", markSheetDirty);
promptFilenameInput.addEventListener("input", markSheetDirty);
promptTemplateInput.addEventListener("input", markSheetDirty);
savePromptButton.addEventListener("click", savePromptTemplate);
loadSavedPromptButton.addEventListener("click", showSavedPromptPicker);

textSourceForm.addEventListener("submit", createWorkbookSource);
textSheetForm.addEventListener("submit", runActiveSheet);
addTextSheetButton.addEventListener("click", addTextSheet);
duplicateTextSheetButton.addEventListener("click", duplicateActiveSheet);
textSheetTabsScrollLeft.addEventListener("click", () => textSheetTabs.scrollBy({ left: -260, behavior: "smooth" }));
textSheetTabsScrollRight.addEventListener("click", () => textSheetTabs.scrollBy({ left: 260, behavior: "smooth" }));
textSheetTabs.addEventListener("scroll", updateSheetTabScrollButtons);

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

textTableViewport.addEventListener("scroll", () => {
  textWorkbookHeader.style.transform = `translateX(${-textTableViewport.scrollLeft}px)`;
  window.requestAnimationFrame(() => loadVisibleWindow(visibleOffset()));
});

pauseTextQueueButton.addEventListener("click", () => setQueuePaused(true));
resumeTextQueueButton.addEventListener("click", () => setQueuePaused(false));
retryFailedRowsButton.addEventListener("click", retryFailedRows);

async function loadWorkbook(preferredSheetId = "") {
  try {
    const response = await fetch(withProject("/api/text/workbook"));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not load the text workbook.");
    workbookState = { source: payload.source || null, sheets: payload.sheets || [] };
    renderSourceState();
    if (!workbookState.source) return;
    const requested = preferredSheetId || activeSheetId;
    const selected = workbookState.sheets.find((sheet) => sheet.sheet_id === requested) || workbookState.sheets[0];
    if (selected) await selectTextSheet(selected.sheet_id, { skipSave: true, force: true });
  } catch (error) {
    setTextStatus(error.message || "Could not load the text workbook.", "failed");
  }
}

function renderSourceState() {
  const source = workbookState.source;
  sourceSetupPanel.classList.toggle("hidden", Boolean(source));
  sourceSummaryPanel.classList.toggle("hidden", !source);
  textWorkbookPanel.classList.toggle("hidden", !source);
  if (!source) return;
  sourceFilenameLabel.textContent = source.source_filename || "Spreadsheet";
  sourceDetailsLabel.textContent = `${Number(source.row_count || 0).toLocaleString()} records | ${Number((source.columns || []).length).toLocaleString()} original columns`;
  frozenMappingList.innerHTML = (source.column_mappings || [])
    .map(
      (mapping) => `
        <div class="text-frozen-mapping">
          <strong>${escapeHtml(mapping.column_name)}</strong>
          <span>${escapeHtml(mapping.prompt_label)}</span>
        </div>
      `
    )
    .join("");
  textExportLink.href = withProject("/api/text/export");
  renderTextSheetTabs();
  renderWorkbookHeader();
}

async function createWorkbookSource(event) {
  event.preventDefault();
  const file = spreadsheetInput.files[0];
  const mappings = collectMappings();
  if (!file) return setTextStatus("Choose a CSV or XLSX file.", "failed");
  if (!inspectedColumns.length) return setTextStatus("Wait for CEREBRO to inspect the spreadsheet headers.", "failed");
  if (!mappings.length) return setTextStatus("Add at least one column mapping.", "failed");
  const confirmed = await CEREBROUI.confirm({
    title: "Create and freeze project workbook",
    message: `Use ${file.name} with ${mappings.length} selected input column${mappings.length === 1 ? "" : "s"}?`,
    details: ["The source file and column mapping cannot be changed inside this project after creation.", "Every sheet in this project will reuse these selected input columns."],
    confirmLabel: "Create and freeze workbook",
  });
  if (!confirmed) return;
  createTextWorkbookButton.disabled = true;
  try {
    setTextStatus("Creating workbook...", "running");
    const body = new FormData();
    body.append("project_id", currentProjectId);
    body.append("spreadsheet", file, file.name);
    body.append("column_mappings", JSON.stringify(mappings));
    body.append("study_id_column", studyIdColumnInput.value.trim());
    body.append("rq_model_preset", modelPresetSelect.value);
    body.append("rq_prompt_filename", "Animal_studies_1.txt");
    const response = await fetch("/api/text/source", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not create the workbook.");
    setTextStatus(`Loaded ${Number(payload.source?.row_count || 0).toLocaleString()} records.`, "complete");
    await loadWorkbook(payload.sheet?.sheet_id || "");
  } catch (error) {
    setTextStatus(error.message || "Could not create the workbook.", "failed");
  } finally {
    createTextWorkbookButton.disabled = false;
  }
}

function renderTextSheetTabs() {
  textSheetTabs.innerHTML = workbookState.sheets
    .map(
      (sheet) => `
        <button class="sheet-tab ${sheet.sheet_id === activeSheetId ? "active" : ""}" type="button" data-sheet-id="${escapeAttribute(sheet.sheet_id)}" role="tab" aria-selected="${sheet.sheet_id === activeSheetId ? "true" : "false"}">
          ${escapeHtml(sheet.name || "Sheet")}
        </button>
      `
    )
    .join("");
  textSheetTabs.querySelectorAll("[data-sheet-id]").forEach((button) => {
    button.addEventListener("click", () => selectTextSheet(button.dataset.sheetId || ""));
  });
  window.requestAnimationFrame(updateSheetTabScrollButtons);
}

async function selectTextSheet(sheetId, options = {}) {
  if (!sheetId || sheetId === activeSheetId && !options.force) return;
  if (!options.skipSave && sheetDirty) await saveActiveSheet({ quiet: true });
  const sheet = workbookState.sheets.find((item) => item.sheet_id === sheetId);
  if (!sheet) return;
  activeSheetId = sheetId;
  sheetDirty = false;
  window.clearTimeout(autosaveTimer);
  renderTextSheetTabs();
  renderActiveSheet(sheet);
  activeStatusFilter = "all";
  textSearchQuery = "";
  textSearchInput.value = "";
  textTableViewport.scrollTop = 0;
  textTableViewport.scrollLeft = 0;
  textWorkbookHeader.style.transform = "translateX(0)";
  windowRequestKey = "";
  await Promise.all([refreshCounts(), loadVisibleWindow(0, { force: true })]);
  if (!sheet.is_locked && !sheet.rq_system_prompt) {
    await loadPromptTemplate(sheet.rq_prompt_filename || "Animal_studies_1.txt");
  }
}

function renderActiveSheet(sheet) {
  const locked = Boolean(sheet.is_locked);
  textSheetNameInput.value = sheet.name || "Sheet";
  modelPresetSelect.value = sheet.rq_model_preset || modelPresetSelect.options[0]?.value || "";
  promptFilenameInput.value = sheet.rq_prompt_filename || "";
  promptTemplateInput.value = sheet.rq_system_prompt || "";
  textSheetLockNotice.classList.toggle("hidden", !locked);
  for (const field of [textSheetNameInput, modelPresetSelect, promptFilenameInput, promptTemplateInput, loadSavedPromptButton, savePromptButton]) {
    field.disabled = locked;
  }
  const apiKeyInput = openaiApiKeyField.querySelector("input");
  if (apiKeyInput) apiKeyInput.disabled = locked;
  runTextSheetButton.disabled = locked;
  const exactState = sheet.status || (locked ? "locked" : "draft");
  runTextSheetButton.textContent = locked ? "Sheet locked" : "Run this sheet";
  duplicateTextSheetButton.disabled = false;
  textSheetSaveStatus.textContent = locked ? "Prompt and model preserved from the first run." : "Sheet changes save automatically.";
  textSheetSaveStatus.className = "queue-hint";
  textSheetProvenanceSummary.textContent = locked
    ? `${sentenceCase(exactState)} | ${sheet.rq_model_preset || "Model preserved"} | ${sheet.rq_prompt_filename || "Prompt preserved"}`
    : "Draft sheet. Prompt and model changes save automatically.";
  setTextSheetSetupCollapsed(locked);
  setPromptStatus("", "");
  renderSelectedModelPreset();
}

function markSheetDirty() {
  const sheet = activeSheet();
  if (!sheet || sheet.is_locked) return;
  sheetDirty = true;
  textSheetSaveStatus.textContent = "Saving changes...";
  textSheetSaveStatus.className = "queue-hint queued";
  const activeTab = textSheetTabs.querySelector(`[data-sheet-id="${cssEscape(activeSheetId)}"]`);
  if (activeTab && textSheetNameInput.value.trim()) activeTab.textContent = textSheetNameInput.value.trim();
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(() => saveActiveSheet({ quiet: true }), 700);
}

async function saveActiveSheet(options = {}) {
  const sheet = activeSheet();
  if (!sheet || sheet.is_locked || sheetSaveInFlight || (!sheetDirty && !options.force)) return sheet;
  const name = textSheetNameInput.value.trim();
  if (!name) {
    textSheetSaveStatus.textContent = "Sheet name is required.";
    textSheetSaveStatus.className = "queue-hint failed";
    return null;
  }
  sheetSaveInFlight = true;
  try {
    const body = sheetFormData();
    const response = await fetch(`/api/text/sheets/${encodeURIComponent(activeSheetId)}`, { method: "PUT", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not save the sheet.");
    workbookState.sheets = payload.sheets || workbookState.sheets;
    sheetDirty = false;
    textSheetSaveStatus.textContent = "Saved.";
    textSheetSaveStatus.className = "queue-hint complete";
    updateActiveTabLabel(payload.sheet?.name || name);
    return payload.sheet;
  } catch (error) {
    textSheetSaveStatus.textContent = error.message || "Could not save the sheet.";
    textSheetSaveStatus.className = "queue-hint failed";
    if (!options.quiet) setTextStatus(error.message || "Could not save the sheet.", "failed");
    return null;
  } finally {
    sheetSaveInFlight = false;
  }
}

async function addTextSheet() {
  if (!workbookState.source) return;
  addTextSheetButton.disabled = true;
  try {
    const body = new FormData();
    body.append("project_id", currentProjectId);
    body.append("rq_model_preset", modelPresetSelect.value || modelPresets[0]?.id || "qwen35_9b_8bit_reasoning");
    const response = await fetch("/api/text/sheets", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not add a sheet.");
    workbookState.sheets = payload.sheets || [];
    activeSheetId = "";
    await selectTextSheet(payload.sheet.sheet_id, { skipSave: true });
  } catch (error) {
    setTextStatus(error.message || "Could not add a sheet.", "failed");
  } finally {
    addTextSheetButton.disabled = false;
  }
}

async function duplicateActiveSheet() {
  if (!activeSheetId) return;
  duplicateTextSheetButton.disabled = true;
  try {
    if (sheetDirty) await saveActiveSheet({ quiet: true });
    const body = projectFormData();
    const response = await fetch(`/api/text/sheets/${encodeURIComponent(activeSheetId)}/duplicate`, { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not duplicate the sheet.");
    workbookState.sheets = payload.sheets || [];
    activeSheetId = "";
    await selectTextSheet(payload.sheet.sheet_id, { skipSave: true });
    setTextStatus(`Created ${payload.sheet.name}.`, "complete");
  } catch (error) {
    setTextStatus(error.message || "Could not duplicate the sheet.", "failed");
  } finally {
    duplicateTextSheetButton.disabled = false;
  }
}

async function runActiveSheet(event) {
  event.preventDefault();
  const sheet = activeSheet();
  if (!sheet || sheet.is_locked) return;
  if (!promptTemplateInput.value.trim()) return setTextStatus("Enter or load a system prompt before running the sheet.", "failed");
  const saved = await saveActiveSheet({ force: true });
  if (!saved) return;
  const confirmed = await CEREBROUI.confirm({
    title: "Run and lock this sheet",
    message: `Create one extraction job per spreadsheet row for ${saved.name || "this sheet"}?`,
    details: ["The prompt and model become read-only when the run starts.", "Duplicate the sheet later to test another prompt or model."],
    confirmLabel: "Run and lock sheet",
  });
  if (!confirmed) return;
  runTextSheetButton.disabled = true;
  try {
    setTextStatus("Creating row jobs for this sheet...", "running");
    const body = sheetFormData();
    const apiKeyInput = openaiApiKeyField.querySelector("input");
    body.append("openai_api_key", apiKeyInput?.value || "");
    const response = await fetch(`/api/text/sheets/${encodeURIComponent(activeSheetId)}/run`, { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not run this sheet.");
    replaceSheet(payload.sheet);
    renderActiveSheet(payload.sheet);
    setTextStatus(`Queued ${Number(payload.count || 0).toLocaleString()} row jobs for ${payload.sheet.name}.`, "queued");
    await Promise.all([refreshCounts(), loadVisibleWindow(0, { force: true })]);
    scheduleTextPolling(0);
  } catch (error) {
    setTextStatus(error.message || "Could not run this sheet.", "failed");
    runTextSheetButton.disabled = false;
  }
}

function setTextSheetSetupCollapsed(collapsed) {
  textSheetSetupBody?.classList.toggle("hidden", collapsed);
  toggleTextSheetSetupButton?.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (toggleTextSheetSetupButton) toggleTextSheetSetupButton.textContent = collapsed ? "View prompt and settings" : "Hide prompt and settings";
}

function sheetFormData() {
  const body = projectFormData();
  body.append("name", textSheetNameInput.value.trim());
  body.append("rq_model_preset", modelPresetSelect.value);
  body.append("rq_prompt_filename", promptFilenameInput.value.trim());
  body.append("rq_system_prompt", promptTemplateInput.value);
  return body;
}

function projectFormData() {
  const body = new FormData();
  body.append("project_id", currentProjectId);
  if (activeSheetId) body.append("sheet_id", activeSheetId);
  return body;
}

function activeSheet() {
  return workbookState.sheets.find((sheet) => sheet.sheet_id === activeSheetId) || null;
}

function replaceSheet(sheet) {
  workbookState.sheets = workbookState.sheets.map((item) => (item.sheet_id === sheet.sheet_id ? sheet : item));
  renderTextSheetTabs();
}

function updateActiveTabLabel(name) {
  const tab = textSheetTabs.querySelector(`[data-sheet-id="${cssEscape(activeSheetId)}"]`);
  if (tab) tab.textContent = name;
}

function updateSheetTabScrollButtons() {
  const maxScroll = Math.max(0, textSheetTabs.scrollWidth - textSheetTabs.clientWidth);
  textSheetTabsScrollLeft.disabled = textSheetTabs.scrollLeft <= 1;
  textSheetTabsScrollRight.disabled = textSheetTabs.scrollLeft >= maxScroll - 1;
}

function renderWorkbookHeader() {
  if (!workbookState.source) return;
  const columns = workbookColumns();
  const template = workbookGridTemplate(columns);
  const width = workbookGridWidth(columns);
  const letters = columns.slice(1).map((_column, index) => `<span class="excel-column-letter" aria-hidden="true">${excelColumnName(index + 1)}</span>`).join("");
  const labels = columns
    .slice(1)
    .map((column) => `<span class="text-workbook-column-label" role="columnheader" title="${escapeAttribute(column.title || column.label)}">${escapeHtml(column.label)}</span>`)
    .join("");
  textWorkbookHeader.style.width = `${width}px`;
  textWorkbookHeader.innerHTML = `
    <div class="text-workbook-header-row" role="presentation" style="grid-template-columns:${template}">
      <span class="excel-corner-cell"></span>${letters}
    </div>
    <div class="text-workbook-header-row text-workbook-label-row" role="row" style="grid-template-columns:${template}">
      <span class="excel-row-number">1</span>${labels}
    </div>
  `;
  textVirtualSpacer.style.width = `${width}px`;
  textVirtualRows.style.width = `${width}px`;
}

function workbookColumns() {
  const mappings = workbookState.source?.column_mappings || [];
  return [
    { key: "row", label: "", width: 54 },
    { key: "status", label: "Status", width: 118 },
    { key: "record_id", label: workbookState.source?.study_id_column || "Record ID", width: 180 },
    ...mappings.map((mapping) => ({
      key: `mapped:${mapping.column_name}`,
      label: mapping.column_name,
      title: `Prompt label: ${mapping.prompt_label}`,
      width: 260,
    })),
    { key: "result", label: "CEREBRO output", width: 280 },
    { key: "actions", label: "Actions", width: 128 },
  ];
}

function workbookGridTemplate(columns = workbookColumns()) {
  return columns.map((column) => `${column.width}px`).join(" ");
}

function workbookGridWidth(columns = workbookColumns()) {
  return columns.reduce((sum, column) => sum + column.width, 0);
}

function excelColumnName(index) {
  let value = index;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function startPolling() {
  scheduleTextPolling(0);
}

function scheduleTextPolling(delay = null) {
  window.clearTimeout(textPollingTimer);
  const active = Boolean(lastTextCounts.running || lastTextCounts.queued);
  const nextDelay = delay ?? (document.hidden ? 30000 : active ? 2500 : 15000);
  textPollingTimer = window.setTimeout(async () => {
    await refreshCounts();
    await refreshVisibleWindow();
    scheduleTextPolling();
  }, nextDelay);
}

async function refreshCounts() {
  if (!activeSheetId) return;
  try {
    const response = await fetch(withProject(`/api/text/jobs/counts?sheet_id=${encodeURIComponent(activeSheetId)}`));
    const payload = await response.json().catch(() => ({}));
    if (response.ok) renderCounts(payload.counts || {}, payload.queue || {});
  } catch (_error) {
    return;
  }
}

function renderCounts(counts, queue) {
  const normalized = {
    total: Number(counts.total || 0),
    not_run: Number(counts.not_run || 0),
    queued: Number(counts.queued || 0),
    running: Number(counts.running || 0),
    completed: Number(counts.completed || 0),
    failed: Number(counts.failed || 0),
  };
  lastTextCounts = normalized;
  const metrics = [
    ["Total", normalized.total, ""],
    ["Completed", normalized.completed, "complete"],
    ["Running", normalized.running, "running"],
    ["Queued", normalized.queued, "queued"],
    ["Failed", normalized.failed, "failed"],
    ["Not run", normalized.not_run, ""],
  ];
  textCounts.innerHTML = metrics.map(([label, value, tone]) => `<div class="stat-card ${tone}"><span>${label}</span><strong>${value.toLocaleString()}</strong></div>`).join("");
  textQueueBadge.textContent = normalized.total ? `${normalized.completed.toLocaleString()} / ${normalized.total.toLocaleString()} complete` : "No rows";
  textQueueBadge.className = `badge ${normalized.failed ? "failed" : normalized.running ? "running" : normalized.queued ? "queued" : normalized.completed ? "complete" : ""}`;
  const queueState = queue.paused ? "Shared text queue paused. " : "";
  textStatusLine.textContent = `${queueState}${normalized.completed.toLocaleString()} completed, ${normalized.running.toLocaleString()} running, ${normalized.queued.toLocaleString()} queued, ${normalized.failed.toLocaleString()} failed.`;
  pauseTextQueueButton.disabled = Boolean(queue.paused);
  resumeTextQueueButton.disabled = !queue.paused;
  updateFilterCounts(normalized);
}

function updateFilterCounts(counts) {
  const values = { all: counts.total, not_run: counts.not_run, queued: counts.queued, running: counts.running, completed: counts.completed, failed: counts.failed };
  document.querySelectorAll("[data-text-count]").forEach((item) => {
    item.textContent = Number(values[item.dataset.textCount] || 0).toLocaleString();
  });
}

async function refreshVisibleWindow() {
  if (!activeSheetId) return;
  const offset = loadedWindow.offset >= 0 ? loadedWindow.offset : visibleOffset();
  await loadVisibleWindow(offset, { force: true, quiet: true });
}

async function loadVisibleWindow(offset = visibleOffset(), options = {}) {
  if (!activeSheetId) return;
  const safeOffset = Math.max(0, offset);
  const key = `${activeSheetId}:${safeOffset}:${activeStatusFilter}:${textSearchQuery}`;
  if (!options.force && key === windowRequestKey) return;
  if (!options.force && loadedWindow.offset <= safeOffset && safeOffset < loadedWindow.offset + Math.max(1, loadedWindow.limit - 40)) return;
  windowRequestKey = key;
  try {
    const params = new URLSearchParams({
      project_id: currentProjectId,
      sheet_id: activeSheetId,
      offset: String(safeOffset),
      limit: String(WINDOW_LIMIT),
      status: activeStatusFilter,
      search: textSearchQuery,
    });
    const response = await fetch(`/api/text/jobs?${params.toString()}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not load rows.");
    totalRows = Number(payload.total || 0);
    loadedWindow = { offset: Number(payload.offset || 0), limit: Number(payload.limit || WINDOW_LIMIT), items: payload.items || [] };
    renderVirtualRows();
    renderFilterButtons();
  } catch (error) {
    if (!options.quiet) setTextStatus(error.message || "Could not load rows.", "failed");
  }
}

function visibleOffset() {
  return Math.max(0, Math.floor(textTableViewport.scrollTop / ROW_HEIGHT) - SCROLL_OVERSCAN);
}

function renderVirtualRows() {
  renderWorkbookHeader();
  const columns = workbookColumns();
  const template = workbookGridTemplate(columns);
  const width = workbookGridWidth(columns);
  textVirtualSpacer.style.height = `${Math.max(1, totalRows) * ROW_HEIGHT}px`;
  textVirtualSpacer.style.width = `${width}px`;
  textVirtualRows.style.width = `${width}px`;
  textWorkbookTableShell?.setAttribute("aria-rowcount", String(totalRows));
  textWorkbookTableShell?.setAttribute("aria-colcount", String(columns.length - 1));
  if (!totalRows) {
    textVirtualRows.innerHTML = `<div class="text-workbook-empty"><strong>No rows match the current filters.</strong></div>`;
    textVirtualSpacer.style.height = "160px";
    return renderFilterSummary(0);
  }
  textVirtualRows.innerHTML = "";
  loadedWindow.items.forEach((item, index) => {
    const rowIndex = loadedWindow.offset + index;
    const cells = columns.slice(1).map((column) => workbookCell(column, item)).join("");
    const row = document.createElement("div");
    row.className = "text-workbook-data-row";
    row.setAttribute("role", "row");
    row.style.gridTemplateColumns = template;
    row.style.transform = `translateY(${rowIndex * ROW_HEIGHT}px)`;
    row.innerHTML = `<span class="excel-row-number" aria-hidden="true">${escapeHtml(Number(item.row || rowIndex + 1) + 1)}</span>${cells}`;
    row.querySelector("[data-action='view']")?.addEventListener("click", (event) => showRowOutput(item.job_id, event.currentTarget));
    row.querySelector("[data-action='retry']")?.addEventListener("click", () => retryRow(item.job_id));
    textVirtualRows.appendChild(row);
  });
  renderFilterSummary(totalRows);
}

function workbookCell(column, item) {
  if (column.key === "status") {
    return `<span class="text-workbook-cell" role="gridcell"><span class="status-badge ${statusClass(item.status)}">${escapeHtml(item.status_label || item.status)}</span></span>`;
  }
  if (column.key === "record_id") {
    return `<span class="text-workbook-cell" role="gridcell" title="${escapeAttribute(item.record_id || "")}">${escapeHtml(item.record_id || "")}</span>`;
  }
  if (column.key.startsWith("mapped:")) {
    const name = column.key.slice(7);
    const value = item.mapped_cells?.[name] || "";
    return `<span class="text-workbook-cell" role="gridcell" title="${escapeAttribute(value)}">${escapeHtml(value)}</span>`;
  }
  if (column.key === "result") {
    const value = item.result_preview || item.error || "";
    return `<span class="text-workbook-cell" role="gridcell" title="${escapeAttribute(value)}">${escapeHtml(value)}</span>`;
  }
  if (column.key === "actions") {
    const hasJob = Boolean(item.job_id);
    return `<span class="text-workbook-cell text-workbook-actions" role="gridcell"><button type="button" data-action="view" ${hasJob ? "" : "disabled"}>View</button><button type="button" data-action="retry" ${item.status === "failed" ? "" : "disabled"}>Retry</button></span>`;
  }
  return `<span class="text-workbook-cell" role="gridcell"></span>`;
}

function renderFilterButtons() {
  textStatusFilterButtons.forEach((button) => {
    const active = button.dataset.textStatusFilter === activeStatusFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  clearTextSearchButton.disabled = !textSearchQuery.trim();
}

function renderFilterSummary(visibleTotal) {
  const searchText = textSearchQuery.trim() ? ` matching "${textSearchQuery.trim()}"` : "";
  const filterText = activeStatusFilter === "all" ? "rows" : `${activeStatusFilter.replace("_", " ")} rows`;
  textFilterSummaryLine.textContent = `Showing ${Number(visibleTotal).toLocaleString()} ${filterText}${searchText}.`;
}

async function showRowOutput(jobId, trigger) {
  if (!jobId) return;
  const inspector = CEREBROUI.openInspector({ kicker: "Text extraction row", title: "Row output", subtitle: jobId, trigger });
  try {
    const response = await fetch(withProject(`/api/text/jobs/${encodeURIComponent(jobId)}/output?sheet_id=${encodeURIComponent(activeSheetId)}`));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not load row output.");
    const metadata = payload.metadata || {};
    inspector.setSubtitle(metadata.record_id || jobId);
    inspector.setContent(`
      <div class="text-output-tabs">
        <details open><summary>Output</summary><pre>${escapeHtml(payload.output || "No output yet.")}</pre></details>
        <details><summary>User prompt</summary><pre>${escapeHtml(payload.user_prompt || "")}</pre></details>
        <details><summary>System prompt</summary><pre>${escapeHtml(payload.system_prompt || "")}</pre></details>
        <details><summary>Metadata</summary><pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre></details>
      </div>
    `);
  } catch (error) {
    inspector.setContent(`<p class="queue-error">${escapeHtml(error.message || "Could not load row output.")}</p>`);
  }
}

async function retryRow(jobId) {
  if (!jobId) return;
  try {
    const response = await fetch(`/api/text/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST", body: projectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not retry row.");
    setTextStatus("Row queued with its original prompt and model.", "queued");
    await Promise.all([refreshCounts(), refreshVisibleWindow()]);
  } catch (error) {
    setTextStatus(error.message || "Could not retry row.", "failed");
  }
}

async function retryFailedRows() {
  retryFailedRowsButton.disabled = true;
  try {
    const response = await fetch("/api/text/jobs/retry-failed", { method: "POST", body: projectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not retry failed rows.");
    setTextStatus(`Retried ${Number(payload.requeued || 0).toLocaleString()} failed rows.`, "queued");
    await Promise.all([refreshCounts(), refreshVisibleWindow()]);
  } catch (error) {
    setTextStatus(error.message || "Could not retry failed rows.", "failed");
  } finally {
    retryFailedRowsButton.disabled = false;
  }
}

async function setQueuePaused(paused) {
  if (paused) {
    const confirmed = await CEREBROUI.confirm({
      title: "Pause all text processing",
      message: "This shared control prevents new text rows from starting across every text extraction project.",
      details: ["Rows already inside a model call will finish normally."],
      confirmLabel: "Pause all text processing",
    });
    if (!confirmed) return;
  }
  const button = paused ? pauseTextQueueButton : resumeTextQueueButton;
  button.disabled = true;
  try {
    const response = await fetch(`/api/text/queue/${paused ? "pause" : "resume"}`, { method: "POST", body: projectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not update the queue.");
    setTextStatus(paused ? "All text processing paused. Active rows will finish." : "All text processing resumed.", paused ? "queued" : "running");
    await refreshCounts();
    scheduleTextPolling(0);
  } catch (error) {
    setTextStatus(error.message || "Could not update the queue.", "failed");
  } finally {
    button.disabled = false;
  }
}

function addMappingRow(columnName = "", promptLabel = "") {
  const row = document.createElement("div");
  row.className = "column-mapping-row";
  const options = [`<option value="">Select a detected column</option>`]
    .concat(inspectedColumns.map((column) => `<option value="${escapeAttribute(column)}" ${column === columnName ? "selected" : ""}>${escapeHtml(column)}</option>`))
    .join("");
  row.innerHTML = `
    <label class="field"><span>Column name</span><select data-mapping-field="column_name" ${inspectedColumns.length ? "" : "disabled"}>${options}</select></label>
    <label class="field"><span>Prompt label</span><input data-mapping-field="prompt_label" type="text" value="${escapeAttribute(promptLabel)}" placeholder="Abstract" /></label>
    <button class="icon-button remove-mapping-button" type="button" aria-label="Remove column mapping" title="Remove column mapping"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg></button>
  `;
  row.querySelector(".remove-mapping-button").addEventListener("click", () => {
    if (columnMappings.querySelectorAll(".column-mapping-row").length <= 1) {
      row.querySelectorAll("input, select").forEach((input) => { input.value = ""; });
    } else {
      row.remove();
    }
  });
  row.querySelector("[data-mapping-field='column_name']").addEventListener("change", (event) => {
    const labelInput = row.querySelector("[data-mapping-field='prompt_label']");
    if (labelInput && !labelInput.value.trim()) labelInput.value = humanizeColumnName(event.currentTarget.value);
  });
  columnMappings.appendChild(row);
}

function collectMappings() {
  return [...columnMappings.querySelectorAll(".column-mapping-row")]
    .map((row) => ({
      column_name: row.querySelector("[data-mapping-field='column_name']")?.value.trim() || "",
      prompt_label: row.querySelector("[data-mapping-field='prompt_label']")?.value.trim() || "",
    }))
    .filter((mapping) => mapping.column_name || mapping.prompt_label);
}

function updateSpreadsheetSummary() {
  const file = spreadsheetInput.files[0];
  spreadsheetInputSummary.textContent = file ? `${file.name} (${formatBytes(file.size)})` : "No file selected";
}

async function inspectSelectedSpreadsheet() {
  updateSpreadsheetSummary();
  const file = spreadsheetInput.files[0];
  inspectedColumns = [];
  inspectedPreviewRows = [];
  spreadsheetPreviewPanel.classList.add("hidden");
  studyIdColumnInput.innerHTML = '<option value="">Use spreadsheet row number</option>';
  studyIdColumnInput.disabled = true;
  columnMappings.innerHTML = "";
  addMappingRow();
  if (!file) {
    sourceInspectionStatus.textContent = "Choose a spreadsheet to inspect its headers.";
    return;
  }
  sourceInspectionStatus.textContent = "Inspecting spreadsheet headers and sample rows...";
  sourceInspectionStatus.className = "queue-hint running";
  createTextWorkbookButton.disabled = true;
  try {
    const body = new FormData();
    body.append("project_id", currentProjectId);
    body.append("spreadsheet", file, file.name);
    const response = await fetch("/api/text/source/inspect", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not inspect the spreadsheet.");
    inspectedColumns = payload.columns || [];
    inspectedPreviewRows = payload.preview_rows || [];
    studyIdColumnInput.innerHTML = ['<option value="">Use spreadsheet row number</option>']
      .concat(inspectedColumns.map((column) => `<option value="${escapeAttribute(column)}">${escapeHtml(column)}</option>`))
      .join("");
    studyIdColumnInput.disabled = false;
    columnMappings.innerHTML = "";
    addMappingRow();
    renderSpreadsheetPreview();
    sourceInspectionStatus.textContent = `Detected ${inspectedColumns.length.toLocaleString()} columns. Select the fields used to construct each row prompt.`;
    sourceInspectionStatus.className = "queue-hint complete";
  } catch (error) {
    sourceInspectionStatus.textContent = error.message || "Could not inspect the spreadsheet.";
    sourceInspectionStatus.className = "queue-hint failed";
    setTextStatus(sourceInspectionStatus.textContent, "failed");
  } finally {
    createTextWorkbookButton.disabled = false;
  }
}

function renderSpreadsheetPreview() {
  spreadsheetPreviewPanel.classList.toggle("hidden", !inspectedColumns.length);
  spreadsheetInspectionSummary.textContent = `${inspectedColumns.length} columns | first ${inspectedPreviewRows.length} non-empty rows`;
  const visibleColumns = inspectedColumns.slice(0, 8);
  const template = `repeat(${Math.max(1, visibleColumns.length)}, minmax(150px, 1fr))`;
  spreadsheetPreviewTable.innerHTML = `
    <div class="spreadsheet-preview-row header" style="grid-template-columns:${template}">
      ${visibleColumns.map((column) => `<strong>${escapeHtml(column)}</strong>`).join("")}
    </div>
    ${inspectedPreviewRows.map((row) => `
      <div class="spreadsheet-preview-row" style="grid-template-columns:${template}">
        ${visibleColumns.map((column) => `<span title="${escapeAttribute(row[column] || "")}">${escapeHtml(row[column] || "")}</span>`).join("")}
      </div>
    `).join("")}
  `;
}

function humanizeColumnName(value) {
  const text = String(value || "").replaceAll("_", " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function renderSelectedModelPreset() {
  const preset = modelPresets.find((item) => item.id === modelPresetSelect.value);
  const isOpenAI = preset?.settings?.provider === "openai";
  openaiApiKeyField.classList.toggle("hidden", !isOpenAI);
}

async function loadPromptTemplate(filename = "Animal_studies_1.txt") {
  loadSavedPromptButton.disabled = true;
  setPromptStatus("Loading prompt...", "");
  try {
    const response = await fetch(`/api/rq-prompts/${encodeURIComponent(filename)}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Failed to load prompt.");
    promptTemplateInput.value = payload.prompt?.system_prompt || "";
    promptFilenameInput.value = payload.prompt?.filename || filename;
    setPromptStatus(`Loaded ${payload.prompt?.filename || filename}.`, "complete");
    markSheetDirty();
  } catch (error) {
    setPromptStatus(error.message || "Failed to load prompt.", "failed");
  } finally {
    loadSavedPromptButton.disabled = Boolean(activeSheet()?.is_locked);
  }
}

async function savePromptTemplate() {
  savePromptButton.disabled = true;
  try {
    const body = new FormData();
    body.append("filename", promptFilenameInput.value || "");
    body.append("system_prompt", promptTemplateInput.value || "");
    const response = await fetch("/api/rq-prompt", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Failed to save prompt.");
    promptFilenameInput.value = payload.prompt?.filename || promptFilenameInput.value;
    setPromptStatus(`Saved ${payload.prompt?.filename}.`, "complete");
    markSheetDirty();
  } catch (error) {
    setPromptStatus(error.message || "Failed to save prompt.", "failed");
  } finally {
    savePromptButton.disabled = false;
  }
}

async function showSavedPromptPicker() {
  try {
    const response = await fetch("/api/rq-prompts");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Failed to load saved prompts.");
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    const items = (payload.prompts || []).map((prompt) => `<button type="button" class="prompt-choice" data-filename="${escapeAttribute(prompt.filename)}">${escapeHtml(prompt.filename)}</button>`).join("");
    overlay.innerHTML = `<div class="modal"><p>Load saved prompt</p><div class="prompt-choice-list">${items || "<p>No prompt files found.</p>"}</div><div class="modal-actions"><button type="button" data-action="cancel">Cancel</button></div></div>`;
    overlay.querySelector("[data-action='cancel']").addEventListener("click", () => CEREBROUI.hideDialog(overlay));
    overlay.querySelectorAll(".prompt-choice").forEach((button) => button.addEventListener("click", async () => {
      CEREBROUI.hideDialog(overlay);
      await loadPromptTemplate(button.dataset.filename);
    }));
    document.body.appendChild(overlay);
    CEREBROUI.showDialog(overlay, { removeOnClose: true, closeOnBackdrop: true });
  } catch (error) {
    setPromptStatus(error.message || "Failed to load saved prompts.", "failed");
  }
}

function setPromptStatus(message, status) {
  promptStatus.textContent = message;
  promptStatus.className = `prompt-status ${status || ""}`;
}

function setTextStatus(message, tone) {
  textStatusLine.textContent = message;
  textQueueBadge.className = `badge ${tone || ""}`;
  if (tone === "failed") textQueueBadge.textContent = "Attention";
  if (tone === "running") textQueueBadge.textContent = "Working";
  if (tone === "queued") textQueueBadge.textContent = "Queued";
  if (tone === "complete") textQueueBadge.textContent = "Ready";
}

function initializeProjectSidebar() {
  if (currentProjectNameLabel && currentProjectName) currentProjectNameLabel.textContent = currentProjectName;
  sidebarToggle?.addEventListener("click", () => {
    const collapsed = projectSidebar.classList.toggle("collapsed");
    sidebarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  });
  projectsMenuButton?.addEventListener("click", () => {
    const open = projectSidebar.classList.toggle("projects-open");
    projectsMenuButton.setAttribute("aria-expanded", open ? "true" : "false");
  });
  projectsNavItem?.addEventListener("mouseenter", () => projectSidebar.classList.add("projects-hover"));
  projectsNavItem?.addEventListener("mouseleave", () => projectSidebar.classList.remove("projects-hover"));
}

async function loadProjectList() {
  try {
    const response = await fetch("/api/projects");
    const payload = await response.json().catch(() => ({}));
    if (response.ok) renderProjectChoices(payload.projects || []);
  } catch (_error) {
    return;
  }
}

function renderProjectChoices(projects) {
  if (!projectsFlyout) return;
  projectsFlyout.innerHTML = projects.map((project) => `
    <button type="button" class="project-choice ${project.project_id === currentProjectId ? "active" : ""}" data-dashboard-path="${escapeAttribute(project.dashboard_path || "/")}" role="menuitem">
      <strong>${escapeHtml(project.name)}</strong><small>${escapeHtml(project.extraction_type_label || "PDF extraction")}</small>
    </button>
  `).join("");
  projectsFlyout.querySelectorAll(".project-choice").forEach((button) => button.addEventListener("click", () => {
    window.location.href = button.dataset.dashboardPath || "/";
  }));
}

function updateProjectLinks() {
  textExportLink.href = withProject("/api/text/export");
}

function withProject(url) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}project_id=${encodeURIComponent(currentProjectId)}`;
}

function statusClass(status) {
  if (status === "completed" || status === "complete") return "complete";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "not_run") return "not-run";
  return "queued";
}

function sentenceCase(value) {
  const text = String(value || "").replaceAll("_", " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

function formatBytes(size) {
  const bytes = Number(size || 0);
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value || ""));
  return String(value || "").replaceAll('"', '\\"');
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
