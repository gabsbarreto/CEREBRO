const structuredForm = document.querySelector("#structuredJobForm");
const runStructuredButton = document.querySelector("#runStructuredButton");
const pdfInput = document.querySelector("#pdfInput");
const folderInput = document.querySelector("#folderInput");
const chooseFilesButton = document.querySelector("#chooseFilesButton");
const chooseFolderButton = document.querySelector("#chooseFolderButton");
const pdfInputSummary = document.querySelector("#pdfInputSummary");
const folderInputSummary = document.querySelector("#folderInputSummary");
const sheetTabs = document.querySelector("#sheetTabs");
const sheetTabsScrollLeft = document.querySelector("#sheetTabsScrollLeft");
const sheetTabsScrollRight = document.querySelector("#sheetTabsScrollRight");
const addSheetButton = document.querySelector("#addSheetButton");
const saveSheetButton = document.querySelector("#saveSheetButton");
const duplicateSheetButton = document.querySelector("#duplicateSheetButton");
const duplicateWorkbookButton = document.querySelector("#duplicateWorkbookButton");
const deleteSheetButton = document.querySelector("#deleteSheetButton");
const sheetLockNotice = document.querySelector("#sheetLockNotice");
const sheetForm = document.querySelector("#sheetForm");
const sheetNameInput = document.querySelector("#sheetNameInput");
const sheetContextInput = document.querySelector("#sheetContextInput");
const sheetRowUnitInput = document.querySelector("#sheetRowUnitInput");
const columnEditorList = document.querySelector("#columnEditorList");
const addColumnButton = document.querySelector("#addColumnButton");
const pasteColumnsButton = document.querySelector("#pasteColumnsButton");
const exportSheetTextButton = document.querySelector("#exportSheetTextButton");
const sheetFormStatus = document.querySelector("#sheetFormStatus");
const toggleStructuredSchemaButton = document.querySelector("#toggleStructuredSchemaButton");
const structuredSchemaFields = document.querySelector("#structuredSchemaFields");
const structuredColumnInstructions = document.querySelector("#structuredColumnInstructions");
const compiledPromptPreview = document.querySelector("#compiledPromptPreview");
const structuredExportLink = document.querySelector("#structuredExportLink");
const structuredStatusLine = document.querySelector("#structuredStatusLine");
const structuredQueueBadge = document.querySelector("#structuredQueueBadge");
const structuredRowsSummary = document.querySelector("#structuredRowsSummary");
const structuredSearchInput = document.querySelector("#structuredSearchInput");
const clearStructuredSearchButton = document.querySelector("#clearStructuredSearchButton");
const structuredTableHeader = document.querySelector("#structuredTableHeader");
const structuredTableViewport = document.querySelector("#structuredTableViewport");
const structuredVirtualSpacer = document.querySelector("#structuredVirtualSpacer");
const structuredVirtualRows = document.querySelector("#structuredVirtualRows");
const addColumnDivider = document.querySelector("#addColumnDivider");
const structuredJobsList = document.querySelector("#structuredJobsList");
const structuredJobsRows = document.querySelector("#structuredJobsRows");
const structuredJobsHeader = document.querySelector("#structuredJobsHeader");
const structuredJobsSpacer = document.querySelector("#structuredJobsSpacer");
const structuredJobsTableShell = document.querySelector("#structuredJobsTableShell");
const structuredJobsSummary = document.querySelector("#structuredJobsSummary");
const refreshStructuredButton = document.querySelector("#refreshStructuredButton");
const toggleStructuredSetupButton = document.querySelector("#toggleStructuredSetupButton");
const structuredSetupBody = document.querySelector("#structuredSetupBody");
const modelPresetSelect = document.querySelector("#modelPresetSelect");
const openaiApiKeyField = document.querySelector("#openaiApiKeyField");
const openaiInputModeField = document.querySelector("#openaiInputModeField");
const openaiInputFileCheckbox = document.querySelector("#openaiInputFileCheckbox");
const pasteColumnsModal = document.querySelector("#pasteColumnsModal");
const closePasteColumnsButton = document.querySelector("#closePasteColumnsButton");
const pasteColumnsInput = document.querySelector("#pasteColumnsInput");
const pasteColumnsStatus = document.querySelector("#pasteColumnsStatus");
const parseColumnsButton = document.querySelector("#parseColumnsButton");
const exportSheetTextModal = document.querySelector("#exportSheetTextModal");
const closeExportSheetTextButton = document.querySelector("#closeExportSheetTextButton");
const exportSheetTextOutput = document.querySelector("#exportSheetTextOutput");
const exportSheetTextStatus = document.querySelector("#exportSheetTextStatus");
const copySheetTextButton = document.querySelector("#copySheetTextButton");
const downloadSheetTextButton = document.querySelector("#downloadSheetTextButton");
const duplicateWorkbookModal = document.querySelector("#duplicateWorkbookModal");
const closeDuplicateWorkbookButton = document.querySelector("#closeDuplicateWorkbookButton");
const cancelDuplicateWorkbookButton = document.querySelector("#cancelDuplicateWorkbookButton");
const confirmDuplicateWorkbookButton = document.querySelector("#confirmDuplicateWorkbookButton");
const duplicateWorkbookSelectAll = document.querySelector("#duplicateWorkbookSelectAll");
const duplicateWorkbookSheetList = document.querySelector("#duplicateWorkbookSheetList");
const duplicateWorkbookStatus = document.querySelector("#duplicateWorkbookStatus");
const currentProjectId = document.body.dataset.currentProjectId || document.querySelector("#currentProjectId")?.value || "";
const projectSidebar = document.querySelector("#projectSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const projectsNavItem = document.querySelector("#projectsNavItem");
const projectsMenuButton = document.querySelector("#projectsMenuButton");
const projectsFlyout = document.querySelector("#projectsFlyout");
const currentProjectNameLabel = document.querySelector("#currentProjectName");
const initialProjects = JSON.parse(document.querySelector("#projectData")?.textContent || "[]");
const modelPresets = JSON.parse(document.querySelector("#modelPresetData")?.textContent || "[]");

const ROW_HEIGHT = 32;
const WINDOW_LIMIT = 100;
const SCROLL_OVERSCAN = 10;
const AUTOSAVE_DELAY_MS = 1000;
const BLANK_EXCEL_ROWS = 24;
const MIN_VISIBLE_EXCEL_COLUMNS = 16;
const TRAILING_INACTIVE_EXCEL_COLUMNS = 6;
const EXCEL_ROW_NUMBER_WIDTH = 44;
const EXCEL_SOURCE_WIDTH = 180;
const EXCEL_STATUS_WIDTH = 126;
const EXCEL_PARSE_DATE_WIDTH = 170;
const EXCEL_COLUMN_WIDTH = 180;
const EXCEL_ADD_DIVIDER_WIDTH = 18;
const STRUCTURED_JOB_ROW_HEIGHT = 58;
const STRUCTURED_JOB_WINDOW_LIMIT = 80;
const STRUCTURED_JOB_OVERSCAN = 8;

let sheets = [];
let activeSheet = null;
let jobs = [];
let structuredJobWindow = { offset: -1, limit: STRUCTURED_JOB_WINDOW_LIMIT, total: 0, items: [], sheetId: "" };
let structuredJobCounts = { all: 0, running: 0, queued: 0, completed: 0, failed: 0, parse_error: 0 };
let structuredQueueState = {};
let structuredJobRequestKey = "";
let rowWindow = { offset: -1, limit: 0, items: [], total: 0, search: "", sheetId: "" };
let pollingTimer = null;
let searchDebounceTimer = null;
let autosaveTimer = null;
let hasUnsavedSheetChanges = false;
let isSavingSheet = false;
let isRenderingSheet = false;

document.addEventListener("DOMContentLoaded", async () => {
  initializeProjectSidebar();
  updateProjectLinks();
  renderSelectedModelPreset();
  renderProjectChoices(initialProjects);
  await loadProjectList();
  await loadSheets();
  await refreshJobs();
  await loadRows(0, { force: true });
  startPolling();
});

chooseFilesButton.addEventListener("click", () => pdfInput.click());
chooseFolderButton.addEventListener("click", () => folderInput.click());
pdfInput.addEventListener("change", updateUploadSummaries);
folderInput.addEventListener("change", updateUploadSummaries);
modelPresetSelect.addEventListener("change", renderSelectedModelPreset);
toggleStructuredSetupButton?.addEventListener("click", () => {
  setStructuredSetupCollapsed(!structuredSetupBody.classList.contains("hidden"));
});
toggleStructuredSchemaButton?.addEventListener("click", () => {
  setStructuredSchemaCollapsed(!structuredSchemaFields.classList.contains("hidden"));
});

addSheetButton.addEventListener("click", async () => {
  await createWorkbookSheet();
});
sheetTabsScrollLeft?.addEventListener("click", () => scrollSheetTabs(-1));
sheetTabsScrollRight?.addEventListener("click", () => scrollSheetTabs(1));
sheetTabs?.addEventListener("scroll", updateSheetTabScrollControls);
window.addEventListener("resize", updateSheetTabScrollControls);

saveSheetButton.addEventListener("click", async () => {
  await saveActiveSheet({ silent: false, requireReady: false });
});

duplicateSheetButton?.addEventListener("click", duplicateActiveSheet);
duplicateWorkbookButton?.addEventListener("click", openDuplicateWorkbookDialog);
deleteSheetButton.addEventListener("click", deleteActiveSheet);
addColumnButton.addEventListener("click", () => addSchemaColumn());
addColumnDivider?.addEventListener("click", () => addSchemaColumn({ focusNewColumn: true }));
exportSheetTextButton?.addEventListener("click", exportActiveSheetText);
pasteColumnsButton.addEventListener("click", () => openModal(pasteColumnsModal));
closePasteColumnsButton.addEventListener("click", () => closeModal(pasteColumnsModal));
parseColumnsButton.addEventListener("click", parsePastedColumns);
closeExportSheetTextButton?.addEventListener("click", () => closeModal(exportSheetTextModal));
copySheetTextButton?.addEventListener("click", copyExportedSheetText);
downloadSheetTextButton?.addEventListener("click", downloadExportedSheetText);
closeDuplicateWorkbookButton?.addEventListener("click", () => closeModal(duplicateWorkbookModal));
cancelDuplicateWorkbookButton?.addEventListener("click", () => closeModal(duplicateWorkbookModal));
confirmDuplicateWorkbookButton?.addEventListener("click", duplicateSelectedWorkbookSheets);
duplicateWorkbookSelectAll?.addEventListener("change", () => {
  duplicateWorkbookSheetList?.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.checked = duplicateWorkbookSelectAll.checked;
  });
  updateDuplicateWorkbookSelection();
});
duplicateWorkbookSheetList?.addEventListener("change", updateDuplicateWorkbookSelection);

sheetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveActiveSheet({ silent: false, requireReady: false });
});

for (const input of [sheetNameInput, sheetContextInput, sheetRowUnitInput]) {
  input.addEventListener("input", () => {
    if (isRenderingSheet || !activeSheet) return;
    if (isActiveSheetLocked()) return;
    activeSheet.name = sheetNameInput.value;
    activeSheet.context = sheetContextInput.value;
    activeSheet.row_unit = sheetRowUnitInput.value;
    markSheetDirty({ renderTabs: input === sheetNameInput });
    renderPromptPreview();
  });
}

columnEditorList.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLTextAreaElement)) return;
  const index = Number(target.dataset.columnIndex);
  const field = target.dataset.columnField || "";
  if (!Number.isInteger(index) || !field || !activeSheet?.columns?.[index]) return;
  if (isActiveSheetLocked()) return;
  activeSheet.columns[index][field] = target.value;
  markSheetDirty();
  if (field === "column_name") {
    syncColumnName(index, target.value, { fromCard: true });
    renderStructuredHeader(activeSheet.columns);
    renderRows();
  }
  renderPromptPreview();
});

columnEditorList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-column-index]");
  if (!button) return;
  if (isActiveSheetLocked()) return;
  const index = Number(button.dataset.removeColumnIndex);
  removeSchemaColumn(index);
});

columnEditorList.addEventListener("blur", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.dataset.columnField !== "column_name") return;
  if (isActiveSheetLocked()) return;
  const index = Number(target.dataset.columnIndex);
  ensureColumnName(index);
}, true);

structuredTableHeader.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  const index = Number(target.dataset.columnIndex);
  if (!Number.isInteger(index) || !activeSheet?.columns?.[index]) return;
  if (isActiveSheetLocked()) return;
  syncColumnName(index, target.value, { fromHeader: true });
  markSheetDirty();
  renderPromptPreview();
});

structuredTableHeader.addEventListener("blur", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  const index = Number(target.dataset.columnIndex);
  if (!Number.isInteger(index) || !activeSheet?.columns?.[index]) return;
  if (isActiveSheetLocked()) return;
  ensureColumnName(index);
  renderColumnCards();
  renderRows();
}, true);

refreshStructuredButton.addEventListener("click", async () => {
  await refreshJobs(structuredJobWindow.offset >= 0 ? structuredJobWindow.offset : 0, { force: true });
  await loadRows(visibleOffset(), { force: true });
});

structuredForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitStructuredJobs();
});

structuredTableViewport.addEventListener("scroll", () => {
  syncSpreadsheetHorizontalScroll();
  const offset = visibleOffset();
  if (Math.abs(offset - rowWindow.offset) >= SCROLL_OVERSCAN) {
    loadRows(offset);
  }
});

structuredJobsList.addEventListener("scroll", () => {
  structuredJobsHeader.style.transform = `translateX(${-structuredJobsList.scrollLeft}px)`;
  window.requestAnimationFrame(() => refreshJobs(structuredJobsVisibleOffset()));
});

document.addEventListener("visibilitychange", () => {
  scheduleStructuredPolling(document.hidden ? 30000 : 0);
});

window.addEventListener("resize", positionAddColumnDivider);

structuredSearchInput.addEventListener("input", () => {
  window.clearTimeout(searchDebounceTimer);
  searchDebounceTimer = window.setTimeout(async () => {
    structuredTableViewport.scrollTop = 0;
    await loadRows(0, { force: true });
  }, 250);
});

clearStructuredSearchButton.addEventListener("click", async () => {
  structuredSearchInput.value = "";
  structuredTableViewport.scrollTop = 0;
  await loadRows(0, { force: true });
});

function initializeProjectSidebar() {
  if (currentProjectNameLabel) currentProjectNameLabel.textContent = document.body.dataset.currentProjectName || "";
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
  } catch {
    renderProjectChoices(initialProjects);
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
    button.addEventListener("click", async () => {
      if (hasUnsavedSheetChanges) {
        const saved = await saveActiveSheet({ silent: true, requireReady: false });
        if (!saved) return;
      }
      window.location.href = button.dataset.dashboardPath || `/?project_id=${encodeURIComponent(button.dataset.projectId || "")}`;
    });
  });
}

function updateProjectLinks() {
  if (structuredExportLink) structuredExportLink.href = withProject("/api/structured/export");
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

function renderSelectedModelPreset() {
  const preset = selectedPreset();
  const settings = preset?.settings || {};
  const isOpenAI = settings.provider === "openai";
  openaiApiKeyField?.classList.toggle("hidden", !isOpenAI);
  openaiInputModeField?.classList.toggle("hidden", !isOpenAI);
}

function selectedPreset() {
  return modelPresets.find((preset) => preset.id === modelPresetSelect.value) || modelPresets[0] || null;
}

async function loadSheets() {
  const response = await fetch(withProject("/api/structured/sheets"));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || "Could not load structured sheets.", "failed");
    return;
  }
  sheets = payload.sheets || [];
  if (!sheets.length) {
    await createWorkbookSheet({ silent: true });
    return;
  }
  const previousSheetId = activeSheet?.sheet_id || "";
  activeSheet = sheets.find((sheet) => sheet.sheet_id === previousSheetId) || sheets[0] || null;
  hasUnsavedSheetChanges = false;
  renderActiveSheet();
}

async function createWorkbookSheet(options = {}) {
  if (hasUnsavedSheetChanges) {
    const saved = await saveActiveSheet({ silent: true, requireReady: false });
    if (!saved) return;
  }
  const body = buildProjectFormData();
  body.append("name", nextSheetName());
  body.append("context", "");
  body.append("row_unit", "");
  body.append("columns", JSON.stringify([defaultColumn()]));
  const response = await fetch("/api/structured/sheets", { method: "POST", body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setSheetStatus(payload.detail || "Could not create sheet.", "failed");
    return;
  }
  sheets = payload.sheets || [];
  activeSheet = payload.sheet || sheets[sheets.length - 1] || null;
  hasUnsavedSheetChanges = false;
  renderActiveSheet();
  structuredTableViewport.scrollTop = 0;
  await loadRows(0, { force: true });
  if (!options.silent) setSheetStatus(`Added ${activeSheet?.name || "sheet"}.`, "complete");
}

function renderActiveSheet() {
  isRenderingSheet = true;
  renderSheetTabs();
  if (!activeSheet) {
    sheetNameInput.value = "";
    sheetContextInput.value = "";
    sheetRowUnitInput.value = "";
    columnEditorList.innerHTML = "";
    compiledPromptPreview.textContent = "";
    deleteSheetButton.disabled = true;
    saveSheetButton.disabled = true;
    if (duplicateSheetButton) duplicateSheetButton.disabled = true;
    runStructuredButton.disabled = true;
    applySheetLockState();
    renderStructuredHeader([]);
    renderRows();
    setStructuredSchemaCollapsed(false);
    isRenderingSheet = false;
    return;
  }
  ensureSheetColumns(activeSheet);
  sheetNameInput.value = activeSheet.name || "";
  sheetContextInput.value = activeSheet.context || "";
  sheetRowUnitInput.value = activeSheet.row_unit || "";
  deleteSheetButton.disabled = false;
  saveSheetButton.disabled = isActiveSheetLocked();
  if (duplicateSheetButton) duplicateSheetButton.disabled = false;
  runStructuredButton.disabled = false;
  renderColumnCards();
  renderStructuredHeader(activeSheet.columns || []);
  renderPromptPreview();
  applySheetLockState();
  setStructuredSchemaCollapsed(isActiveSheetLocked());
  isRenderingSheet = false;
}

function renderSheetTabs(options = {}) {
  if (!sheetTabs) return;
  sheetTabs.innerHTML = (sheets || [])
    .map((sheet) => {
      const active = activeSheet?.sheet_id === sheet.sheet_id ? "active" : "";
      return `
        <button class="sheet-tab ${active}" type="button" data-sheet-id="${escapeHtml(sheet.sheet_id)}" role="tab" aria-selected="${active ? "true" : "false"}">
          ${escapeHtml(sheet.name || "Sheet")}
        </button>
      `;
    })
    .join("");
  sheetTabs.querySelectorAll("[data-sheet-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextSheet = sheets.find((sheet) => sheet.sheet_id === button.dataset.sheetId);
      if (!nextSheet || nextSheet.sheet_id === activeSheet?.sheet_id) return;
      if (hasUnsavedSheetChanges) {
        const saved = await saveActiveSheet({ silent: true, requireReady: false });
        if (!saved) return;
      }
      activeSheet = nextSheet;
      hasUnsavedSheetChanges = false;
      renderActiveSheet();
      structuredTableViewport.scrollTop = 0;
      await loadRows(0, { force: true });
    });
  });
  requestAnimationFrame(() => {
    if (options.scrollActive !== false) {
      sheetTabs.querySelector(".sheet-tab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    updateSheetTabScrollControls();
  });
}

function scrollSheetTabs(direction) {
  if (!sheetTabs) return;
  const distance = Math.max(180, Math.floor(sheetTabs.clientWidth * 0.75));
  sheetTabs.scrollBy({ left: direction * distance, behavior: "smooth" });
}

function updateSheetTabScrollControls() {
  if (!sheetTabs || !sheetTabsScrollLeft || !sheetTabsScrollRight) return;
  const maxScroll = Math.max(0, sheetTabs.scrollWidth - sheetTabs.clientWidth);
  const hasOverflow = maxScroll > 1;
  const left = sheetTabs.scrollLeft > 1;
  const right = sheetTabs.scrollLeft < maxScroll - 1;
  sheetTabsScrollLeft.classList.toggle("hidden", !hasOverflow);
  sheetTabsScrollRight.classList.toggle("hidden", !hasOverflow);
  sheetTabsScrollLeft.disabled = !left;
  sheetTabsScrollRight.disabled = !right;
}

function renderColumnCards() {
  const columns = activeSheet?.columns || [];
  const locked = isActiveSheetLocked();
  columnEditorList.innerHTML = columns
    .map((column, index) => {
      const missingQuestion = !String(column.question || "").trim();
      return `
        <div class="structured-column-row ${missingQuestion ? "incomplete" : ""}" data-column-card-index="${index}">
          <div class="column-row-head">
            <label class="field">
              <span>Column name</span>
              <input data-column-field="column_name" data-column-index="${index}" type="text" value="${escapeAttribute(column.column_name || "")}" placeholder="Column${index + 1}" ${locked ? "disabled" : ""} />
            </label>
            <button class="icon-button remove-column-button" type="button" data-remove-column-index="${index}" aria-label="Remove column" title="Remove column" ${locked ? "disabled" : ""}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>
            </button>
          </div>
          <label class="field">
            <span>Question <em>required</em></span>
            <textarea data-column-field="question" data-column-index="${index}" rows="2" placeholder="State exactly what CEREBRO should extract for this column." ${locked ? "disabled" : ""}>${escapeHtml(column.question || "")}</textarea>
          </label>
          <label class="field">
            <span>Rules / expected values / examples</span>
            <textarea data-column-field="rules" data-column-index="${index}" rows="5" placeholder="* If no value is reported, enter NA." ${locked ? "disabled" : ""}>${escapeHtml(column.rules || "")}</textarea>
          </label>
        </div>
      `;
    })
    .join("");
}

function renderPromptPreview() {
  if (!activeSheet) {
    compiledPromptPreview.textContent = "";
    setSheetStatus("Create a sheet to start.", "");
    return;
  }
  const readiness = schemaReadiness(activeSheet);
  if (isActiveSheetLocked()) {
    compiledPromptPreview.textContent = activeSheet.compiled_prompt || activeSheet.schema_error || readiness.message;
    setSheetStatus("Sheet schema is locked for reproducibility. Duplicate it to edit.", "complete");
    return;
  }
  if (hasUnsavedSheetChanges) {
    compiledPromptPreview.textContent = readiness.ready
      ? "Autosave will refresh the generated prompt preview."
      : readiness.message;
    setSheetStatus(readiness.ready ? "Unsaved changes. Autosave pending." : readiness.message, readiness.ready ? "queued" : "failed");
    return;
  }
  if (activeSheet.schema_ready && activeSheet.compiled_prompt) {
    compiledPromptPreview.textContent = activeSheet.compiled_prompt;
    setSheetStatus("Sheet schema is ready.", "complete");
    return;
  }
  compiledPromptPreview.textContent = activeSheet.schema_error || readiness.message;
  setSheetStatus(activeSheet.schema_error || readiness.message, "failed");
}

function addSchemaColumn(options = {}) {
  if (!activeSheet) return;
  if (isActiveSheetLocked()) return;
  ensureSheetColumns(activeSheet);
  activeSheet.columns.push(defaultColumn(activeSheet.columns));
  const newColumnIndex = activeSheet.columns.length - 1;
  markSheetDirty();
  renderColumnCards();
  renderStructuredHeader(activeSheet.columns);
  renderRows();
  renderPromptPreview();
  if (options.focusNewColumn) {
    window.requestAnimationFrame(() => {
      const headerInput = structuredTableHeader.querySelector(`[data-column-index="${newColumnIndex}"]`);
      headerInput?.focus();
      headerInput?.select?.();
    });
  }
}

function removeSchemaColumn(index) {
  if (!activeSheet?.columns?.length) return;
  if (isActiveSheetLocked()) return;
  if (activeSheet.columns.length <= 1) {
    activeSheet.columns = [defaultColumn([], "Column1")];
  } else {
    activeSheet.columns.splice(index, 1);
  }
  markSheetDirty();
  renderColumnCards();
  renderStructuredHeader(activeSheet.columns);
  renderRows();
  renderPromptPreview();
}

function syncColumnName(index, value, options = {}) {
  if (!activeSheet?.columns?.[index]) return;
  activeSheet.columns[index].column_name = value;
  if (!options.fromHeader) {
    const headerInput = structuredTableHeader.querySelector(`[data-column-index="${index}"]`);
    if (headerInput) headerInput.value = value;
  }
  if (!options.fromCard) {
    const cardInput = columnEditorList.querySelector(`[data-column-field="column_name"][data-column-index="${index}"]`);
    if (cardInput) cardInput.value = value;
  }
}

function ensureColumnName(index) {
  if (!Number.isInteger(index) || !activeSheet?.columns?.[index]) return;
  if (String(activeSheet.columns[index].column_name || "").trim()) return;
  const otherColumns = activeSheet.columns.filter((_column, columnIndex) => columnIndex !== index);
  const fallback = nextColumnName(otherColumns);
  syncColumnName(index, fallback);
  markSheetDirty();
  renderStructuredHeader(activeSheet.columns);
}

async function saveActiveSheet(options = {}) {
  if (!activeSheet) return false;
  if (isActiveSheetLocked()) {
    setSheetStatus("Sheet schema is locked for reproducibility. Duplicate it to edit.", "complete");
    return !options.requireReady;
  }
  activeSheet.name = sheetNameInput.value.trim();
  activeSheet.context = sheetContextInput.value.trim();
  activeSheet.row_unit = sheetRowUnitInput.value.trim();
  activeSheet.columns = collectColumnsFromState();
  const readiness = schemaReadiness(activeSheet);
  if (options.requireReady && !readiness.ready) {
    setSheetStatus(readiness.message, "failed");
    setStatus(readiness.message, "failed");
    return false;
  }
  if (!activeSheet.name) {
    setSheetStatus("Sheet name is required.", "failed");
    return false;
  }
  window.clearTimeout(autosaveTimer);
  isSavingSheet = true;
  setSheetStatus("Saving...", "queued");
  const body = buildProjectFormData();
  body.append("name", activeSheet.name);
  body.append("context", activeSheet.context || "");
  body.append("row_unit", activeSheet.row_unit || "");
  body.append("columns", JSON.stringify(activeSheet.columns));
  let response;
  try {
    response = await fetch(`/api/structured/sheets/${encodeURIComponent(activeSheet.sheet_id)}`, {
      method: "PUT",
      body,
    });
  } catch (error) {
    isSavingSheet = false;
    setSheetStatus(error.message || "Could not save sheet.", "failed");
    return false;
  }
  const payload = await response.json().catch(() => ({}));
  isSavingSheet = false;
  if (!response.ok) {
    const message = payload.detail || "Could not save sheet.";
    setSheetStatus(message, "failed");
    if (!options.silent) setStatus(message, "failed");
    return false;
  }
  sheets = payload.sheets || [];
  activeSheet = payload.sheet || activeSheet;
  hasUnsavedSheetChanges = false;
  renderSheetTabs({ scrollActive: !options.autosave });
  applySheetLockState();
  if (!options.autosave) renderActiveSheet();
  if (options.autosave) renderPromptPreview();
  if (!options.silent) {
    const savedReadiness = schemaReadiness(activeSheet);
    setSheetStatus(
      savedReadiness.ready ? `Saved ${activeSheet.name}.` : `Saved draft. ${savedReadiness.message}`,
      savedReadiness.ready ? "complete" : "queued",
    );
  } else if (options.autosave) {
    setSheetStatus("Saved", "complete");
  }
  return true;
}

async function deleteActiveSheet() {
  if (!activeSheet) return;
  const confirmed = await CEREBROUI.confirm({
    title: "Delete structured worksheet",
    message: `Delete ${activeSheet.name || "this worksheet"}?`,
    details: ["Its parsed rows and parse errors will be removed from this workbook."],
    confirmLabel: "Delete worksheet",
    danger: true,
  });
  if (!confirmed) return;
  const response = await fetch(withProject(`/api/structured/sheets/${encodeURIComponent(activeSheet.sheet_id)}`), { method: "DELETE" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || "Could not delete sheet.", "failed");
    return;
  }
  sheets = payload.sheets || [];
  activeSheet = sheets[0] || null;
  hasUnsavedSheetChanges = false;
  if (!activeSheet) {
    await createWorkbookSheet({ silent: true });
    return;
  }
  renderActiveSheet();
  await loadRows(0, { force: true });
}

async function duplicateActiveSheet() {
  if (!activeSheet) return;
  if (hasUnsavedSheetChanges && !isActiveSheetLocked()) {
    const saved = await saveActiveSheet({ silent: true, requireReady: false });
    if (!saved) return;
  }
  const body = buildProjectFormData();
  const response = await fetch(`/api/structured/sheets/${encodeURIComponent(activeSheet.sheet_id)}/duplicate`, {
    method: "POST",
    body,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setSheetStatus(payload.detail || "Could not duplicate sheet.", "failed");
    return;
  }
  sheets = payload.sheets || [];
  activeSheet = payload.sheet || sheets[sheets.length - 1] || null;
  hasUnsavedSheetChanges = false;
  renderActiveSheet();
  structuredTableViewport.scrollTop = 0;
  await loadRows(0, { force: true });
  setSheetStatus(`Duplicated ${activeSheet?.name || "sheet"}.`, "complete");
}

async function openDuplicateWorkbookDialog() {
  if (hasUnsavedSheetChanges && !isActiveSheetLocked()) {
    const saved = await saveActiveSheet({ silent: true, requireReady: false });
    if (!saved) return;
  }
  duplicateWorkbookSheetList.innerHTML = (sheets || [])
    .map((sheet) => {
      const columnCount = Array.isArray(sheet.columns) ? sheet.columns.length : 0;
      const detail = `${columnCount} column${columnCount === 1 ? "" : "s"}${sheet.is_locked ? " - run" : " - editable"}`;
      return `
        <label class="duplicate-workbook-sheet-option">
          <input type="checkbox" value="${escapeAttribute(sheet.sheet_id || "")}" checked />
          <span>
            <strong>${escapeHtml(sheet.name || "Sheet")}</strong>
            <small>${escapeHtml(detail)}</small>
          </span>
        </label>
      `;
    })
    .join("");
  duplicateWorkbookStatus.textContent = "";
  duplicateWorkbookStatus.className = "prompt-status";
  updateDuplicateWorkbookSelection();
  openModal(duplicateWorkbookModal);
}

function updateDuplicateWorkbookSelection() {
  const checkboxes = Array.from(duplicateWorkbookSheetList?.querySelectorAll('input[type="checkbox"]') || []);
  const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
  if (duplicateWorkbookSelectAll) {
    duplicateWorkbookSelectAll.checked = Boolean(checkboxes.length) && selectedCount === checkboxes.length;
    duplicateWorkbookSelectAll.indeterminate = selectedCount > 0 && selectedCount < checkboxes.length;
  }
  if (confirmDuplicateWorkbookButton) confirmDuplicateWorkbookButton.disabled = selectedCount === 0;
  if (duplicateWorkbookStatus && selectedCount > 0) {
    duplicateWorkbookStatus.textContent = `${selectedCount} sheet${selectedCount === 1 ? "" : "s"} selected.`;
    duplicateWorkbookStatus.className = "prompt-status";
  } else if (duplicateWorkbookStatus) {
    duplicateWorkbookStatus.textContent = "Select at least one sheet.";
    duplicateWorkbookStatus.className = "prompt-status";
  }
}

async function duplicateSelectedWorkbookSheets() {
  const selectedSheetIds = Array.from(duplicateWorkbookSheetList?.querySelectorAll('input[type="checkbox"]:checked') || [])
    .map((checkbox) => checkbox.value)
    .filter(Boolean);
  if (!selectedSheetIds.length) {
    duplicateWorkbookStatus.textContent = "Select at least one sheet to duplicate.";
    duplicateWorkbookStatus.className = "prompt-status failed";
    return;
  }
  confirmDuplicateWorkbookButton.disabled = true;
  duplicateWorkbookStatus.textContent = "Creating workbook copy...";
  duplicateWorkbookStatus.className = "prompt-status queued";
  const body = buildProjectFormData();
  body.append("sheet_ids", JSON.stringify(selectedSheetIds));
  try {
    const response = await fetch("/api/structured/workbook/duplicate", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not duplicate workbook.");
    const dashboardPath = payload.project?.dashboard_path;
    if (!dashboardPath) throw new Error("The new workbook was created without a dashboard path.");
    duplicateWorkbookStatus.textContent = `Created ${payload.project.name}. Opening workbook...`;
    duplicateWorkbookStatus.className = "prompt-status complete";
    window.location.assign(dashboardPath);
  } catch (error) {
    duplicateWorkbookStatus.textContent = error.message || "Could not duplicate workbook.";
    duplicateWorkbookStatus.className = "prompt-status failed";
    confirmDuplicateWorkbookButton.disabled = false;
  }
}

async function exportActiveSheetText() {
  if (!activeSheet) return;
  if (hasUnsavedSheetChanges && !isActiveSheetLocked()) {
    const saved = await saveActiveSheet({ silent: true, requireReady: false });
    if (!saved) return;
  }
  const response = await fetch(withProject(`/api/structured/sheets/${encodeURIComponent(activeSheet.sheet_id)}/import-text`));
  const text = await response.text();
  if (!response.ok) {
    let message = text || "Could not export sheet text.";
    try {
      message = JSON.parse(text).detail || message;
    } catch (_error) {
      // The endpoint normally returns text/plain; keep the raw response as fallback.
    }
    setSheetStatus(message, "failed");
    return;
  }
  exportSheetTextOutput.value = text;
  exportSheetTextStatus.textContent = "Sheet text is ready to copy or download.";
  exportSheetTextStatus.className = "prompt-status complete";
  openModal(exportSheetTextModal);
  exportSheetTextOutput.focus();
  exportSheetTextOutput.select();
}

async function copyExportedSheetText() {
  const text = exportSheetTextOutput?.value || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    exportSheetTextOutput.focus();
    exportSheetTextOutput.select();
    document.execCommand("copy");
  }
  exportSheetTextStatus.textContent = "Copied sheet text.";
  exportSheetTextStatus.className = "prompt-status complete";
}

function downloadExportedSheetText() {
  const text = exportSheetTextOutput?.value || "";
  if (!text) return;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${downloadSafeName(activeSheet?.name || "structured-sheet")}_structured_sheet.txt`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  exportSheetTextStatus.textContent = "Downloaded sheet text.";
  exportSheetTextStatus.className = "prompt-status complete";
}

async function parsePastedColumns() {
  if (!activeSheet) return;
  if (isActiveSheetLocked()) {
    pasteColumnsStatus.textContent = "This sheet schema is locked for reproducibility. Duplicate it to import changes.";
    pasteColumnsStatus.className = "prompt-status failed";
    return;
  }
  const body = new FormData();
  body.append("project_id", currentProjectId);
  body.append("sheet_id", activeSheet.sheet_id || "");
  body.append("block_text", pasteColumnsInput.value);
  body.append("current_name", sheetNameInput.value || "");
  body.append("current_context", sheetContextInput.value || "");
  body.append("current_row_unit", sheetRowUnitInput.value || "");
  body.append("current_columns", JSON.stringify(collectColumnsFromState()));
  const response = await fetch("/api/structured/sheets/parse-import", { method: "POST", body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    pasteColumnsStatus.textContent = payload.detail || "Could not parse import text.";
    pasteColumnsStatus.className = "prompt-status failed";
    return;
  }
  if (payload.has_conflicts) {
    const overwrite = await confirmImportOverwrite(payload.conflicts || {});
    if (!overwrite) {
      pasteColumnsStatus.textContent = "Import cancelled.";
      pasteColumnsStatus.className = "prompt-status";
      return;
    }
  }
  applySheetImport(payload);
  markSheetDirty({ renderTabs: Boolean((payload.fields || {}).name) });
  renderColumnCards();
  renderStructuredHeader(activeSheet.columns);
  renderRows();
  renderPromptPreview();
  pasteColumnsStatus.textContent = `Imported ${payload.count || 0} column${payload.count === 1 ? "" : "s"}.`;
  pasteColumnsStatus.className = "prompt-status complete";
  closeModal(pasteColumnsModal);
}

function applySheetImport(payload) {
  const fields = payload.fields || {};
  if (Object.prototype.hasOwnProperty.call(fields, "name")) {
    activeSheet.name = fields.name || activeSheet.name;
    sheetNameInput.value = activeSheet.name;
  }
  if (Object.prototype.hasOwnProperty.call(fields, "context")) {
    activeSheet.context = fields.context || "";
    sheetContextInput.value = activeSheet.context;
  }
  if (Object.prototype.hasOwnProperty.call(fields, "row_unit")) {
    activeSheet.row_unit = fields.row_unit || "";
    sheetRowUnitInput.value = activeSheet.row_unit;
  }
  const importedColumns = payload.columns || [];
  if (!activeSheet.columns) activeSheet.columns = [];
  for (const importedColumn of importedColumns) {
    const importedName = String(importedColumn.column_name || "").trim();
    const existingIndex = activeSheet.columns.findIndex((column) => String(column.column_name || "").trim() === importedName);
    const normalized = {
      column_name: importedName,
      question: String(importedColumn.question || "").trim(),
      rules: String(importedColumn.rules || "").trim(),
    };
    if (existingIndex >= 0) {
      activeSheet.columns[existingIndex] = normalized;
    } else {
      activeSheet.columns.push(normalized);
    }
  }
  ensureSheetColumns(activeSheet);
}

function confirmImportOverwrite(conflicts) {
  const fields = conflicts.fields || [];
  const columns = conflicts.columns || [];
  const details = [];
  if (fields.length) details.push(`Fields: ${fields.join(", ")}`);
  if (columns.length) details.push(`Columns: ${columns.map((column) => `"${column}"`).join(", ")}`);
  return CEREBROUI.confirm({
    title: "Import conflicts found",
    message: "The following information already exists in this sheet. Overwrite it with the imported text?",
    details,
    confirmLabel: "Overwrite",
  });
}

async function submitStructuredJobs() {
  if (!activeSheet) {
    setStatus("Create or select a structured sheet first.", "failed");
    return;
  }
  if (isActiveSheetLocked()) {
    const readiness = schemaReadiness(activeSheet);
    if (!readiness.ready) {
      setStatus(readiness.message, "failed");
      return;
    }
  } else {
    const saved = await saveActiveSheet({ silent: true, requireReady: true });
    if (!saved) return;
  }
  const files = collectPdfFiles();
  if (!files.length) {
    setStatus("Choose at least one PDF.", "failed");
    return;
  }
  if (!isActiveSheetLocked()) {
    const confirmed = await CEREBROUI.confirm({
      title: "Run and lock this sheet",
      message: `Queue ${files.length} PDF${files.length === 1 ? "" : "s"} using ${activeSheet.name || "this sheet"}?`,
      details: ["The sheet schema becomes read-only when the first job is queued.", "Duplicate the sheet later to test a different schema."],
      confirmLabel: "Run and lock sheet",
    });
    if (!confirmed) return;
  }
  runStructuredButton.disabled = true;
  try {
    const body = buildUploadFormData(files);
    const response = await fetch("/api/structured/jobs", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Could not queue structured PDF jobs.");
    if (payload.sheet) {
      activeSheet = payload.sheet;
      sheets = (sheets || []).map((sheet) => (sheet.sheet_id === activeSheet.sheet_id ? activeSheet : sheet));
      renderActiveSheet();
    }
    setStatus(`Queued ${payload.count || 0} structured PDF job${payload.count === 1 ? "" : "s"}.`, "queued");
    setSheetStatus(`Queued ${payload.count || 0} job${payload.count === 1 ? "" : "s"}. Sheet schema is now locked for reproducibility.`, "complete");
    clearFileInputs();
    await refreshJobs();
    structuredTableViewport.scrollTop = 0;
    await loadRows(0, { force: true });
  } catch (error) {
    setStatus(error.message || "Could not queue structured PDF jobs.", "failed");
  } finally {
    runStructuredButton.disabled = false;
  }
}

function buildUploadFormData(files) {
  const body = buildSettingsFormData();
  body.append("sheet_id", activeSheet.sheet_id);
  for (const file of files) {
    body.append("pdfs", file, uploadName(file));
    body.append("pdf_relative_paths", file.webkitRelativePath || file.name);
  }
  return body;
}

function buildSettingsFormData() {
  const body = buildProjectFormData();
  const data = new FormData(structuredForm);
  for (const field of ["ocr_dpi", "ocr_batch_size", "deepseek_ocr_model_path", "rq_model_preset", "openai_api_key"]) {
    if (data.has(field)) body.append(field, data.get(field) || "");
  }
  const isOpenAI = selectedPreset()?.settings?.provider === "openai";
  body.append("openai_input_mode", isOpenAI && openaiInputFileCheckbox?.checked ? "pdf_file" : "ocr_text");
  return body;
}

function collectPdfFiles() {
  const byKey = new Map();
  for (const file of [...pdfInput.files, ...folderInput.files]) {
    if (!file.name.toLowerCase().endsWith(".pdf")) continue;
    const key = `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`;
    byKey.set(key, file);
  }
  return [...byKey.values()];
}

function updateUploadSummaries() {
  pdfInputSummary.textContent = uploadSummary([...pdfInput.files], "No files selected", "PDF");
  folderInputSummary.textContent = uploadSummary([...folderInput.files], "No folder selected", "PDF in folder");
}

function uploadSummary(files, emptyText, singularLabel) {
  const pdfFiles = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
  if (!pdfFiles.length) return emptyText;
  if (pdfFiles.length === 1) return `1 ${singularLabel}: ${displayUploadName(pdfFiles[0])}`;
  return `${pdfFiles.length} PDFs selected`;
}

function clearFileInputs() {
  pdfInput.value = "";
  folderInput.value = "";
  updateUploadSummaries();
}

function uploadName(file) {
  return file.name || "uploaded.pdf";
}

function displayUploadName(file) {
  return file.webkitRelativePath || file.name || "PDF";
}

function startPolling() {
  scheduleStructuredPolling(0);
}

function scheduleStructuredPolling(delay = null) {
  window.clearTimeout(pollingTimer);
  const active = Boolean(
    structuredJobCounts.running ||
    structuredJobCounts.queued ||
    structuredQueueState.pending_count ||
    structuredQueueState.openai_pending_count ||
    structuredQueueState.openai_running_count ||
    (structuredQueueState.current_job_ids || []).length
  );
  const nextDelay = delay ?? (document.hidden ? 30000 : active ? 3000 : 15000);
  pollingTimer = window.setTimeout(async () => {
    await refreshJobs(structuredJobWindow.offset >= 0 ? structuredJobWindow.offset : 0, { force: true });
    await loadRows(visibleOffset(), { force: true });
    scheduleStructuredPolling();
  }, nextDelay);
}

async function refreshJobs(offset = structuredJobsVisibleOffset(), options = {}) {
  const safeOffset = Math.max(0, Number(offset || 0));
  const sheetId = activeSheet?.sheet_id || "";
  const requestKey = `${sheetId}:${safeOffset}`;
  if (!options.force && requestKey === structuredJobRequestKey) return;
  if (!options.force && structuredJobWindow.offset <= safeOffset && safeOffset < structuredJobWindow.offset + Math.max(1, structuredJobWindow.limit - 30)) return;
  structuredJobRequestKey = requestKey;
  const params = new URLSearchParams({
    project_id: currentProjectId,
    sheet_id: sheetId,
    offset: String(safeOffset),
    limit: String(STRUCTURED_JOB_WINDOW_LIMIT),
  });
  const response = await fetch(`/api/structured/jobs?${params.toString()}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || "Could not load structured jobs.", "failed");
    return;
  }
  jobs = payload.items || payload.jobs || [];
  structuredJobWindow = {
    offset: Number(payload.offset || 0),
    limit: Number(payload.limit || STRUCTURED_JOB_WINDOW_LIMIT),
    total: Number(payload.total || 0),
    items: jobs,
    sheetId,
  };
  structuredJobCounts = { ...structuredJobCounts, ...(payload.counts || {}) };
  structuredQueueState = payload.queue || {};
  renderJobs(payload.queue || {});
  if (structuredJobCounts.all && !structuredSetupBody.classList.contains("setup-initialized")) {
    setStructuredSetupCollapsed(true);
    structuredSetupBody.classList.add("setup-initialized");
  }
}

function renderJobs(queue) {
  const running = Number(queue.openai_running_count || 0) + Number(queue.current_job_ids?.length || (queue.current_job_id ? 1 : 0));
  const pending = Number(queue.pending_count || 0) + Number(queue.openai_pending_count || 0);
  const completed = Number(structuredJobCounts.completed || 0);
  const failed = Number(structuredJobCounts.failed || 0) + Number(structuredJobCounts.parse_error || 0);
  structuredQueueBadge.textContent = `${Number(structuredJobCounts.all || 0).toLocaleString()} job${structuredJobCounts.all === 1 ? "" : "s"}`;
  structuredQueueBadge.className = `badge ${failed ? "failed" : running ? "running" : pending ? "queued" : completed ? "complete" : ""}`;
  structuredJobsTableShell?.setAttribute("aria-rowcount", String(structuredJobWindow.total));
  structuredJobsSummary.textContent = activeSheet
    ? `${Number(structuredJobWindow.total).toLocaleString()} jobs for ${activeSheet.name || "this sheet"}; ${Number(structuredJobCounts.parse_error || 0).toLocaleString()} parse errors.`
    : "Select a sheet to view its jobs.";
  structuredJobsSpacer.style.height = `${Math.max(1, structuredJobWindow.total) * STRUCTURED_JOB_ROW_HEIGHT}px`;
  structuredJobsRows.innerHTML = "";
  if (!structuredJobWindow.total) {
    structuredJobsSpacer.style.height = "140px";
    structuredJobsRows.innerHTML = `<p class="structured-job-empty">No structured PDF jobs for this sheet.</p>`;
    return;
  }
  structuredJobWindow.items.forEach((job, index) => {
    const status = job.status || {};
    const metadata = job.metadata || {};
    const parseStatus = metadata.structured_parse_status || "Pending";
    const parseError = metadata.structured_parse_error || "";
    const row = document.createElement("div");
    row.className = `structured-job-data-row ${statusClass(status.status || parseStatus)}`;
    row.style.transform = `translateY(${(structuredJobWindow.offset + index) * STRUCTURED_JOB_ROW_HEIGHT}px)`;
    row.setAttribute("role", "row");
    row.innerHTML = `
      <span class="structured-job-cell" role="gridcell" title="${escapeAttribute(job.filename || metadata.original_filename || job.job_id)}">${escapeHtml(job.filename || metadata.original_filename || job.job_id)}</span>
      <span class="structured-job-cell" role="gridcell"><span class="status-badge ${statusClass(status.status)}">${escapeHtml(status.status || "queued")}</span></span>
      <span class="structured-job-cell" role="gridcell" title="${escapeAttribute(parseError)}"><span class="status-badge ${statusClass(parseStatus)}">${escapeHtml(parseStatus)}</span></span>
      <span class="structured-job-cell" role="gridcell" title="${escapeAttribute(metadata.rq_screening_model || "")}">${escapeHtml(metadata.rq_screening_model || "Not recorded")}</span>
      <span class="structured-job-cell structured-job-action" role="gridcell"><button type="button" data-job-id="${escapeAttribute(job.job_id)}">View</button></span>
    `;
    row.querySelector("[data-job-id]")?.addEventListener("click", (event) => showJobResult(job.job_id, event.currentTarget));
    structuredJobsRows.appendChild(row);
  });
}

function structuredJobsVisibleOffset() {
  return Math.max(0, Math.floor((structuredJobsList?.scrollTop || 0) / STRUCTURED_JOB_ROW_HEIGHT) - STRUCTURED_JOB_OVERSCAN);
}

function setStructuredSetupCollapsed(collapsed) {
  structuredSetupBody?.classList.toggle("hidden", collapsed);
  toggleStructuredSetupButton?.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (toggleStructuredSetupButton) toggleStructuredSetupButton.textContent = collapsed ? "Configure new run" : "Hide setup";
}

function setStructuredSchemaCollapsed(collapsed) {
  structuredSchemaFields?.classList.toggle("hidden", collapsed);
  structuredColumnInstructions?.classList.toggle("hidden", collapsed);
  toggleStructuredSchemaButton?.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (toggleStructuredSchemaButton) toggleStructuredSchemaButton.textContent = collapsed ? "View schema details" : "Hide schema details";
}

async function loadRows(offset = visibleOffset(), options = {}) {
  if ((activeSheet?.sheet_id || "") !== structuredJobWindow.sheetId) {
    structuredJobsList.scrollTop = 0;
    await refreshJobs(0, { force: true });
  }
  if (!activeSheet?.sheet_id) {
    rowWindow = { offset: 0, limit: WINDOW_LIMIT, items: [], total: 0, search: "", sheetId: "" };
    renderRows();
    return;
  }
  const search = structuredSearchInput.value.trim();
  const safeOffset = Math.max(0, offset);
  if (!options.force && rowWindow.offset === safeOffset && rowWindow.search === search && rowWindow.sheetId === activeSheet.sheet_id) {
    return;
  }
  const params = new URLSearchParams({
    project_id: currentProjectId,
    sheet_id: activeSheet.sheet_id,
    offset: String(safeOffset),
    limit: String(WINDOW_LIMIT),
    search,
  });
  const response = await fetch(`/api/structured/rows?${params.toString()}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    structuredRowsSummary.textContent = payload.detail || "Could not load structured rows.";
    return;
  }
  rowWindow = {
    offset: payload.offset || 0,
    limit: payload.limit || WINDOW_LIMIT,
    items: payload.items || [],
    total: payload.total || 0,
    search,
    sheetId: activeSheet.sheet_id,
  };
  renderRows();
}

function visibleOffset() {
  return Math.max(0, Math.floor(structuredTableViewport.scrollTop / ROW_HEIGHT) - SCROLL_OVERSCAN);
}

function renderStructuredHeader(columns) {
  const safeColumns = columns || [];
  const locked = isActiveSheetLocked();
  const inactiveCount = inactiveColumnCount(safeColumns);
  const template = gridTemplateForColumns(safeColumns);
  const width = tableWidth(safeColumns);
  structuredTableHeader.style.minWidth = width;
  structuredVirtualRows.style.width = width;
  structuredVirtualSpacer.style.width = width;
  structuredTableHeader.innerHTML = `
    <div class="structured-excel-row structured-excel-letters" style="grid-template-columns: ${template};">
      <span class="excel-corner-cell"></span>
      ${Array.from({ length: 3 + safeColumns.length + inactiveCount }, (_name, index) => {
        const inactiveClass = index >= 3 + safeColumns.length ? " inactive-excel-column" : "";
        return `<span class="excel-column-letter${inactiveClass}">${escapeHtml(excelColumnLabel(index))}</span>`;
      })
        .join("")}
    </div>
    <div class="structured-excel-row structured-excel-header-row" style="grid-template-columns: ${template};">
      <span class="excel-row-number">1</span>
      <span class="structured-header-fixed excel-cell">Source PDF</span>
      <span class="structured-header-fixed excel-cell">Parse status</span>
      <span class="structured-header-fixed excel-cell">Parse date</span>
      ${safeColumns
        .map(
          (column, index) => `
            <label class="structured-header-cell excel-cell">
              <input class="structured-column-name-input" data-column-index="${index}" type="text" value="${escapeAttribute(column.column_name || "")}" placeholder="Column${index + 1}" aria-label="Column ${index + 1} name" ${locked ? "disabled" : ""} />
            </label>
          `
        )
        .join("")}
      ${Array.from({ length: inactiveCount }, () => `<span class="excel-cell inactive-excel-cell"></span>`).join("")}
    </div>
  `;
  syncSpreadsheetHorizontalScroll();
}

function renderRows() {
  const columns = activeSheet?.columns || [];
  const inactiveCount = inactiveColumnCount(columns);
  const width = tableWidth(columns);
  const renderedRowCount = Math.max(rowWindow.total, BLANK_EXCEL_ROWS);
  structuredVirtualSpacer.style.height = `${renderedRowCount * ROW_HEIGHT}px`;
  structuredVirtualSpacer.style.width = width;
  structuredVirtualRows.style.width = width;
  structuredRowsSummary.textContent = activeSheet
    ? `Showing ${rowWindow.total} row${rowWindow.total === 1 ? "" : "s"} for ${activeSheet.name}.`
    : "No sheet selected.";
  if (!activeSheet) {
    structuredVirtualRows.innerHTML = renderBlankRows(columns, BLANK_EXCEL_ROWS, 0);
    positionAddColumnDivider();
    return;
  }
  if (!rowWindow.items.length) {
    structuredVirtualRows.innerHTML = renderBlankRows(columns, BLANK_EXCEL_ROWS, 0);
    positionAddColumnDivider();
    return;
  }
  structuredVirtualRows.innerHTML = "";
  for (const [index, item] of rowWindow.items.entries()) {
    const rowIndex = rowWindow.offset + index;
    const row = document.createElement("div");
    row.className = `structured-table-row structured-table-grid ${statusClass(item.parse_status)}`;
    row.style.top = `${rowIndex * ROW_HEIGHT}px`;
    row.style.gridTemplateColumns = gridTemplateForColumns(columns);
    const cells = item.cells || {};
    row.innerHTML = `
      <span class="excel-row-number">${rowIndex + 2}</span>
      <span class="truncate-cell excel-cell" title="${escapeAttribute(item.source_pdf || "")}">${escapeHtml(item.source_pdf || "")}</span>
      <span class="excel-cell"><span class="status-badge ${statusClass(item.parse_status)}">${escapeHtml(item.parse_status || "")}</span></span>
      <span class="truncate-cell excel-cell" title="${escapeAttribute(item.parse_date || item.extracted_at || "")}">${escapeHtml(formatTimestamp(item.parse_date || item.extracted_at || ""))}</span>
      ${columns
        .map((column) => {
          const value = column.column_name ? cells[column.column_name] : "";
          return `<span class="truncate-cell excel-cell" title="${escapeAttribute(value || item.parse_error || "")}">${escapeHtml(value || item.parse_error || "")}</span>`;
        })
        .join("")}
      ${Array.from({ length: inactiveCount }, () => `<span class="excel-cell inactive-excel-cell"></span>`).join("")}
    `;
    structuredVirtualRows.appendChild(row);
  }
  positionAddColumnDivider();
}

function gridTemplateForColumns(columns) {
  const inactiveCount = inactiveColumnCount(columns || []);
  return [
    `${EXCEL_ROW_NUMBER_WIDTH}px`,
    `${EXCEL_SOURCE_WIDTH}px`,
    `${EXCEL_STATUS_WIDTH}px`,
    `${EXCEL_PARSE_DATE_WIDTH}px`,
    ...(columns || []).map(() => `${EXCEL_COLUMN_WIDTH}px`),
    ...Array.from({ length: inactiveCount }, () => `${EXCEL_COLUMN_WIDTH}px`),
  ].join(" ");
}

function tableWidth(columns) {
  const activeCount = (columns || []).length;
  const inactiveCount = inactiveColumnCount(columns || []);
  return `${EXCEL_ROW_NUMBER_WIDTH + EXCEL_SOURCE_WIDTH + EXCEL_STATUS_WIDTH + EXCEL_PARSE_DATE_WIDTH + (activeCount + inactiveCount) * EXCEL_COLUMN_WIDTH}px`;
}

function renderBlankRows(columns, count, offset) {
  const inactiveCount = inactiveColumnCount(columns || []);
  return Array.from({ length: count }, (_value, index) => {
    const rowIndex = offset + index;
    return `
      <div class="structured-table-row structured-table-grid blank" style="top: ${rowIndex * ROW_HEIGHT}px; grid-template-columns: ${gridTemplateForColumns(columns)};">
        <span class="excel-row-number">${rowIndex + 2}</span>
        <span class="excel-cell"></span>
        <span class="excel-cell"></span>
        <span class="excel-cell"></span>
        ${(columns || []).map(() => `<span class="excel-cell"></span>`).join("")}
        ${Array.from({ length: inactiveCount }, () => `<span class="excel-cell inactive-excel-cell"></span>`).join("")}
      </div>
    `;
  }).join("");
}

function inactiveColumnCount(columns) {
  const activeCount = (columns || []).length;
  return Math.max(TRAILING_INACTIVE_EXCEL_COLUMNS, MIN_VISIBLE_EXCEL_COLUMNS - 3 - activeCount);
}

function syncSpreadsheetHorizontalScroll() {
  const scrollLeft = structuredTableViewport?.scrollLeft || 0;
  structuredTableHeader.style.transform = `translateX(${-scrollLeft}px)`;
  positionAddColumnDivider();
}

function positionAddColumnDivider() {
  if (!addColumnDivider || !activeSheet || isActiveSheetLocked()) {
    addColumnDivider?.classList.add("hidden");
    return;
  }
  const activeColumnCount = (activeSheet.columns || []).length;
  const dividerOffset =
    EXCEL_ROW_NUMBER_WIDTH +
    EXCEL_SOURCE_WIDTH +
    EXCEL_STATUS_WIDTH +
    EXCEL_PARSE_DATE_WIDTH +
    activeColumnCount * EXCEL_COLUMN_WIDTH;
  const scrollLeft = structuredTableViewport?.scrollLeft || 0;
  addColumnDivider.style.left = `${dividerOffset - scrollLeft - EXCEL_ADD_DIVIDER_WIDTH / 2}px`;
  addColumnDivider.classList.remove("hidden");
}

function excelColumnLabel(index) {
  let value = index + 1;
  let label = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

async function showJobResult(jobId, trigger) {
  if (!jobId) return;
  const inspector = CEREBROUI.openInspector({
    kicker: "Structured PDF job",
    title: "Job output",
    subtitle: jobId,
    trigger,
  });
  const response = await fetch(withProject(`/api/structured/jobs/${encodeURIComponent(jobId)}/result`));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    inspector.setContent(`<p class="queue-error">${escapeHtml(payload.detail || "Could not load job result.")}</p>`);
    return;
  }
  const metadata = payload.metadata || {};
  inspector.setSubtitle(metadata.original_filename || jobId);
  inspector.setContent(`
    <div class="structured-result-stack">
      <p><strong>Parse status:</strong> ${escapeHtml(metadata.structured_parse_status || "pending")}</p>
      ${metadata.structured_parse_error ? `<p class="queue-error">${escapeHtml(metadata.structured_parse_error)}</p>` : ""}
      <details open><summary>Raw TSV output</summary><pre>${escapeHtml(payload.raw_output || "")}</pre></details>
      <details><summary>Parsed rows JSON</summary><pre>${escapeHtml(JSON.stringify(payload.parsed_rows || [], null, 2))}</pre></details>
      <details><summary>Parse errors JSON</summary><pre>${escapeHtml(JSON.stringify(payload.parse_errors || [], null, 2))}</pre></details>
      <details><summary>Compiled prompt</summary><pre>${escapeHtml(payload.system_prompt || "")}</pre></details>
    </div>
  `);
}

function collectColumnsFromState() {
  return (activeSheet?.columns || []).map((column) => ({
    column_name: String(column.column_name || "").trim(),
    question: String(column.question || "").trim(),
    rules: String(column.rules || "").trim(),
  }));
}

function schemaReadiness(sheet) {
  const columns = collectColumnsFromStateFor(sheet);
  if (!String(sheet.name || "").trim()) return { ready: false, message: "Sheet name is required." };
  if (!columns.length) return { ready: false, message: "Add at least one column." };
  const seen = new Set();
  for (const [index, column] of columns.entries()) {
    const label = column.column_name || `Column ${index + 1}`;
    if (!column.column_name) return { ready: false, message: `${label} needs a name.` };
    if (seen.has(column.column_name)) return { ready: false, message: `Duplicate column name: ${column.column_name}` };
    if (!column.question) return { ready: false, message: `${label} needs a question before extraction can run.` };
    seen.add(column.column_name);
  }
  return { ready: true, message: "Sheet schema is ready." };
}

function collectColumnsFromStateFor(sheet) {
  return (sheet?.columns || []).map((column) => ({
    column_name: String(column.column_name || "").trim(),
    question: String(column.question || "").trim(),
    rules: String(column.rules || "").trim(),
  }));
}

function ensureSheetColumns(sheet) {
  if (!sheet.columns || !sheet.columns.length) {
    sheet.columns = [defaultColumn()];
  }
}

function isActiveSheetLocked() {
  return Boolean(activeSheet?.is_locked || String(activeSheet?.locked_at || "").trim());
}

function applySheetLockState() {
  const locked = isActiveSheetLocked();
  const hasSheet = Boolean(activeSheet);
  sheetNameInput.disabled = locked || !hasSheet;
  sheetContextInput.disabled = locked || !hasSheet;
  sheetRowUnitInput.disabled = locked || !hasSheet;
  addColumnButton.disabled = locked || !hasSheet;
  pasteColumnsButton.disabled = locked || !hasSheet;
  if (exportSheetTextButton) exportSheetTextButton.disabled = !hasSheet;
  saveSheetButton.disabled = locked || !hasSheet || isSavingSheet;
  if (duplicateSheetButton) duplicateSheetButton.disabled = !hasSheet;
  if (duplicateWorkbookButton) duplicateWorkbookButton.disabled = !hasSheet;
  sheetLockNotice?.classList.toggle("hidden", !locked);
  if (locked) {
    addColumnDivider?.classList.add("hidden");
  } else {
    positionAddColumnDivider();
  }
}

function defaultColumn(existingColumns = [], explicitName = "") {
  return { column_name: explicitName || nextColumnName(existingColumns), question: "", rules: "" };
}

function nextColumnName(existingColumns = activeSheet?.columns || []) {
  const names = new Set((existingColumns || []).map((column) => String(column.column_name || "")));
  let index = names.size + 1;
  while (names.has(`Column${index}`)) index += 1;
  return `Column${index}`;
}

function nextSheetName() {
  const names = new Set((sheets || []).map((sheet) => String(sheet.name || "")));
  let index = sheets.length + 1;
  while (names.has(`Sheet ${index}`)) index += 1;
  return `Sheet ${index}`;
}

function downloadSafeName(value) {
  return String(value || "structured-sheet")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "structured-sheet";
}

function markSheetDirty(options = {}) {
  if (isActiveSheetLocked()) {
    setSheetStatus("Sheet schema is locked for reproducibility. Duplicate it to edit.", "complete");
    return;
  }
  hasUnsavedSheetChanges = true;
  if (options.renderTabs) renderSheetTabs({ scrollActive: false });
  saveSheetButton.classList.add("queued");
  scheduleAutosave();
}

function setSheetStatus(message, tone = "") {
  sheetFormStatus.textContent = message || "";
  sheetFormStatus.className = `section-subtitle prompt-status ${tone || ""}`.trim();
  saveSheetButton.classList.toggle("queued", hasUnsavedSheetChanges && !isActiveSheetLocked());
  applySheetLockState();
}

function scheduleAutosave() {
  window.clearTimeout(autosaveTimer);
  if (!activeSheet || isActiveSheetLocked()) return;
  autosaveTimer = window.setTimeout(() => {
    saveActiveSheet({ silent: true, requireReady: false, autosave: true });
  }, AUTOSAVE_DELAY_MS);
}

function openModal(modal) {
  CEREBROUI.showDialog(modal, { closeOnBackdrop: true });
}

function closeModal(modal) {
  CEREBROUI.hideDialog(modal);
}

function setStatus(message, tone) {
  structuredStatusLine.textContent = message;
  structuredQueueBadge.textContent = tone === "failed" ? "Error" : tone === "queued" ? "Queued" : tone === "complete" ? "Ready" : "Working";
  structuredQueueBadge.className = `badge ${tone || ""}`;
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value === "complete" || value === "completed" || value === "parsed") return "complete";
  if (value === "failed" || value === "error") return "failed";
  if (value === "running" || value === "openai_running") return "running";
  return "queued";
}

function formatTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
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
  return escapeHtml(value).replaceAll("\n", "&#10;");
}
