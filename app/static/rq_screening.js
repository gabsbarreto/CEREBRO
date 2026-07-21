const form = document.querySelector("#jobForm");
const runButton = document.querySelector("#runButton");
const progressBar = document.querySelector("#progressBar");
const statusLine = document.querySelector("#statusLine");
const jobBadge = document.querySelector("#jobBadge");
const resultPanel = document.querySelector("#resultPanel");
const resultText = document.querySelector("#resultText");
const mergedText = document.querySelector("#mergedText");
const promptText = document.querySelector("#promptText");
const metadataText = document.querySelector("#metadataText");
const downloadLink = document.querySelector("#downloadLink");
const copyButton = document.querySelector("#copyButton");
const pdfInput = document.querySelector("#pdfInput");
const folderInput = document.querySelector("#folderInput");
const chooseFilesButton = document.querySelector("#chooseFilesButton");
const chooseFolderButton = document.querySelector("#chooseFolderButton");
const pdfInputSummary = document.querySelector("#pdfInputSummary");
const folderInputSummary = document.querySelector("#folderInputSummary");
const queuePanel = document.querySelector("#queuePanel");
const queueList = document.querySelector("#queueList");
const queueSummary = document.querySelector("#queueSummary");
const pdfJobTableShell = document.querySelector("#pdfJobTableShell");
const pdfJobTableHeader = document.querySelector("#pdfJobTableHeader");
const pdfJobVirtualSpacer = document.querySelector("#pdfJobVirtualSpacer");
const pdfJobVirtualRows = document.querySelector("#pdfJobVirtualRows");
const togglePdfSetupButton = document.querySelector("#togglePdfSetupButton");
const pdfSetupBody = document.querySelector("#pdfSetupBody");
const batchSummaryLine = document.querySelector("#batchSummaryLine");
const batchStats = document.querySelector("#batchStats");
const activeJobsPanel = document.querySelector("#activeJobsPanel");
const activeJobsList = document.querySelector("#activeJobsList");
const activeWorkersBadge = document.querySelector("#activeWorkersBadge");
const technicalEventsList = document.querySelector("#technicalEventsList");
const autoRefreshStatus = document.querySelector("#autoRefreshStatus");
const refreshQueueButton = document.querySelector("#refreshQueueButton");
const pauseButton = document.querySelector("#pauseButton");
const resumeButton = document.querySelector("#resumeButton");
const retryFailedButton = document.querySelector("#retryFailedButton");
const cleanQueueButton = document.querySelector("#cleanQueueButton");
const cleanQueueHint = document.querySelector("#cleanQueueHint");
const jobFilterButtons = [...document.querySelectorAll("[data-job-filter]")];
const jobSearchInput = document.querySelector("#jobSearchInput");
const clearJobSearchButton = document.querySelector("#clearJobSearchButton");
const filterSummaryLine = document.querySelector("#filterSummaryLine");
const modelPresetSelect = document.querySelector("#modelPresetSelect");
const openaiApiKeyField = document.querySelector("#openaiApiKeyField");
const openaiInputModeField = document.querySelector("#openaiInputModeField");
const openaiInputFileCheckbox = document.querySelector("#openaiInputFileCheckbox");
const promptTemplateInput = document.querySelector("#promptTemplateInput");
const promptFilenameInput = document.querySelector("#promptFilenameInput");
const rqSystemPromptInput = document.querySelector("#rqSystemPromptInput");
const savePromptButton = document.querySelector("#savePromptButton");
const loadSavedPromptButton = document.querySelector("#loadSavedPromptButton");
const promptStatus = document.querySelector("#promptStatus");
const currentProjectId = document.body.dataset.currentProjectId || document.querySelector("#currentProjectId")?.value || "";
const currentProjectName = document.body.dataset.currentProjectName || "";
const currentProjectType = document.body.dataset.currentProjectType || "pdf";
const projectSidebar = document.querySelector("#projectSidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const projectsNavItem = document.querySelector("#projectsNavItem");
const projectsMenuButton = document.querySelector("#projectsMenuButton");
const projectsFlyout = document.querySelector("#projectsFlyout");
const currentProjectNameLabel = document.querySelector("#currentProjectName");
const initialProjects = JSON.parse(document.querySelector("#projectData")?.textContent || "[]");
const modelPresets = JSON.parse(document.querySelector("#modelPresetData")?.textContent || "[]");
const JOB_LIST_LIMIT = 80;
const PDF_JOB_ROW_HEIGHT = 76;
const PDF_JOB_OVERSCAN = 8;

let pollTimer = null;
let currentJobId = null;
let trackedJobs = new Map();
let activeJobRecords = [];
let jobWindow = { offset: -1, limit: JOB_LIST_LIMIT, total: 0, items: [] };
let jobCounts = { all: 0, running: 0, queued: 0, completed: 0, failed: 0 };
let queueState = { paused: false, current_job_id: null, pending_job_ids: [], pending_count: 0 };
let activeStatusFilter = "all";
let jobSearchQuery = "";
let jobSearchTimer = null;
let jobWindowRequestKey = "";
let lastSuccessfulRefreshAt = null;
let lastUpdatedTimer = null;
let currentPollingCadence = "waiting for first update";

document.addEventListener("DOMContentLoaded", () => {
  initializeProjectSidebar();
  updateProjectLinks();
  renderProjectChoices(initialProjects);
  loadProjectList();
  renderSelectedModelPreset();
  updateUploadSummaries();
  loadPromptTemplate();
  startLastUpdatedTimer();
  restoreQueueFromJobList();
});

modelPresetSelect.addEventListener("change", renderSelectedModelPreset);

chooseFilesButton.addEventListener("click", () => {
  pdfInput.click();
});

chooseFolderButton.addEventListener("click", () => {
  folderInput.click();
});

pdfInput.addEventListener("change", updateUploadSummaries);
folderInput.addEventListener("change", updateUploadSummaries);

savePromptButton.addEventListener("click", savePromptTemplate);
loadSavedPromptButton.addEventListener("click", showSavedPromptPicker);

if (refreshQueueButton) {
  refreshQueueButton.addEventListener("click", async () => {
    refreshQueueButton.disabled = true;
    try {
      await restoreQueueFromJobList();
    } finally {
      refreshQueueButton.disabled = false;
    }
  });
}

for (const button of jobFilterButtons) {
  button.addEventListener("click", async () => {
    activeStatusFilter = button.dataset.jobFilter || "all";
    queueList.scrollTop = 0;
    await loadPdfJobWindow(0, { force: true });
  });
}

if (jobSearchInput) {
  jobSearchInput.addEventListener("input", () => {
    window.clearTimeout(jobSearchTimer);
    jobSearchTimer = window.setTimeout(async () => {
      jobSearchQuery = jobSearchInput.value || "";
      queueList.scrollTop = 0;
      await loadPdfJobWindow(0, { force: true });
    }, 250);
  });
}

if (clearJobSearchButton) {
  clearJobSearchButton.addEventListener("click", async () => {
    jobSearchQuery = "";
    if (jobSearchInput) jobSearchInput.value = "";
    queueList.scrollTop = 0;
    await loadPdfJobWindow(0, { force: true });
    jobSearchInput?.focus();
  });
}

queueList?.addEventListener("scroll", () => {
  pdfJobTableHeader.style.transform = `translateX(${-queueList.scrollLeft}px)`;
  window.requestAnimationFrame(() => loadPdfJobWindow(pdfVisibleOffset()));
});

document.addEventListener("visibilitychange", () => {
  schedulePdfPolling(document.hidden ? 30000 : 0);
});

togglePdfSetupButton?.addEventListener("click", () => {
  setPdfSetupCollapsed(!pdfSetupBody.classList.contains("hidden"));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = collectPdfFiles();
  if (!files.length) {
    setStatus("Choose one or more PDF files, or choose a folder containing PDFs.", 0, "failed");
    return;
  }

  runButton.disabled = true;
  resultPanel.classList.add("hidden");
  setStages("");
  try {
    setStatus(`Checking ${files.length} PDF${files.length === 1 ? "" : "s"}`, 0.01, "running");
    const check = await checkExistingUploads(files);
    let filesToRun = files;
    let rerunExisting = false;
    if (check.duplicates?.length) {
      rerunExisting = await askOverwriteDuplicates(check.duplicates);
      if (!rerunExisting) {
        const duplicateNames = new Set(check.duplicates.map((item) => item.filename));
        filesToRun = files.filter((file) => !duplicateNames.has(displayUploadName(file)));
        if (!filesToRun.length) {
          setStatus("No new PDFs to queue.", 0, "queued");
          return;
        }
      }
    }

    setStatus(`Uploading ${filesToRun.length} PDF${filesToRun.length === 1 ? "" : "s"}`, 0.02, "running");
    const body = buildUploadFormData(filesToRun, rerunExisting);
    const response = await fetch("/api/jobs", { method: "POST", body });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "Failed to create jobs.");
    }
    const payload = await response.json();
    if (!payload.jobs?.length) {
      setStatus("No jobs were queued.", 0, "queued");
      return;
    }
    for (const job of payload.jobs || []) {
      trackedJobs.set(job.job_id, {
        job_id: job.job_id,
        filename: job.filename,
        status: "queued",
        stage: "queued",
        progress: 0,
        prompt_filename: job.prompt_filename || "",
        model: job.model || "",
        openai_input_mode: job.openai_input_mode || "",
        reuses_ocr: Boolean(job.reuses_ocr),
        reuses_openai_file: Boolean(job.reuses_openai_file),
      });
    }
    currentJobId = payload.job_id;
    jobBadge.textContent = `${trackedJobs.size} queued`;
    renderQueue();
    startPolling();
    clearFileInputs();
  } catch (error) {
    setStatus(error.message, 1, "failed");
  } finally {
    runButton.disabled = false;
  }
});

copyButton.addEventListener("click", async () => {
  await navigator.clipboard.writeText(resultText.value);
  copyButton.textContent = "Copied";
  window.setTimeout(() => {
    copyButton.textContent = "Copy result";
  }, 1200);
});

pauseButton.addEventListener("click", async () => {
  const confirmed = await CEREBROUI.confirm({
    title: "Pause all PDF processing",
    message: "This shared control pauses standard and structured PDF jobs across every project.",
    details: ["Active PDF workers may be interrupted and returned to the queue."],
    confirmLabel: "Pause all PDF processing",
  });
  if (!confirmed) return;
  pauseButton.disabled = true;
  try {
    const response = await fetch("/api/queue/pause", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) queueState = payload;
    setStatus("All PDF processing paused. Active workers are being returned to the shared queue.", 0, "queued");
    renderQueue();
    startPolling();
    await pollAllStatuses();
  } finally {
    pauseButton.disabled = false;
  }
});

resumeButton.addEventListener("click", async () => {
  resumeButton.disabled = true;
  try {
    const body = buildProjectFormData();
    body.append("preserve_settings", "true");
    const response = await fetch("/api/queue/resume", { method: "POST", body });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) queueState = payload;
    setStatus("All PDF processing resumed with each job's saved settings.", 0, "running");
    renderQueue();
    startPolling();
    await pollAllStatuses();
  } finally {
    resumeButton.disabled = false;
  }
});

retryFailedButton.addEventListener("click", async () => {
  retryFailedButton.disabled = true;
  try {
    const response = await fetch("/api/queue/retry-failed", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Could not retry failed jobs.");
    }
    const skipped = payload.skipped || [];
    const retryMessage = `Retried ${payload.requeued || 0} failed job${payload.requeued === 1 ? "" : "s"} with original saved settings.`;
    setStatus(skipped.length ? `${retryMessage} ${skipped.length} could not be retried.` : retryMessage, 0, skipped.length ? "failed" : "queued");
    mergeJobRecords(payload.jobs || []);
    renderQueue();
    await restoreQueueFromJobList();
    startPolling();
  } catch (error) {
    setStatus(error.message || "Could not retry failed jobs.", 1, "failed");
  } finally {
    retryFailedButton.disabled = false;
  }
});

cleanQueueButton.addEventListener("click", async () => {
  if (!queueState.paused) {
    setStatus("Pause the queue before removing pending jobs.", 0, "queued");
    updateDashboardControls();
    return;
  }
  const confirmed = await CEREBROUI.confirm({
    title: "Remove pending jobs",
    message: "Remove pending PDF jobs from this project? Completed, failed, and running jobs will be kept.",
    confirmLabel: "Remove pending jobs",
    danger: true,
  });
  if (!confirmed) {
    return;
  }
  cleanQueueButton.disabled = true;
  try {
    const response = await fetch("/api/queue/clean", { method: "POST", body: buildProjectFormData() });
    const payload = await response.json().catch(() => ({}));
    setStatus(`Removed ${payload.removed || 0} queued job${payload.removed === 1 ? "" : "s"} from the queue.`, 0, "queued");
    await restoreQueueFromJobList();
    startPolling();
  } finally {
    updateDashboardControls();
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
  const excelReportLink = document.querySelector("#excelReportLink");
  if (excelReportLink) {
    excelReportLink.href = withProject("/api/reports/excel");
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

function renderSelectedModelPreset() {
  const preset = selectedPreset();
  const settings = preset?.settings || {};
  const isOpenAI = settings.provider === "openai";
  openaiApiKeyField.classList.toggle("hidden", !isOpenAI);
  openaiInputModeField.classList.toggle("hidden", !isOpenAI);
  if (openaiInputFileCheckbox) {
    openaiInputFileCheckbox.disabled = !isOpenAI;
  }
}

function selectedPreset() {
  return modelPresets.find((preset) => preset.id === modelPresetSelect.value) || modelPresets[0] || null;
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
    .map(
      (prompt) =>
        `<button type="button" class="prompt-choice" data-filename="${escapeHtml(prompt.filename)}">${escapeHtml(prompt.filename)}</button>`
    )
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
  overlay.querySelector("[data-action='cancel']").addEventListener("click", () => CEREBROUI.hideDialog(overlay));
  overlay.querySelectorAll(".prompt-choice").forEach((button) => {
    button.addEventListener("click", async () => {
      const filename = button.dataset.filename;
      CEREBROUI.hideDialog(overlay);
      await loadPromptTemplate(filename);
    });
  });
  document.body.appendChild(overlay);
  CEREBROUI.showDialog(overlay, { removeOnClose: true, closeOnBackdrop: true });
}

function syncSystemPromptField() {
  rqSystemPromptInput.value = promptTemplateInput.value || "";
}

function setPromptStatus(message, status) {
  promptStatus.textContent = message;
  promptStatus.className = `prompt-status ${status || ""}`;
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
  pdfInputSummary.textContent = uploadSummary([...pdfInput.files], "No files selected", "file");
  folderInputSummary.textContent = uploadSummary([...folderInput.files], "No folder selected", "folder file");
}

function uploadSummary(files, emptyText, singularLabel) {
  const pdfFiles = files.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
  if (!files.length) return emptyText;
  if (!pdfFiles.length) return "No PDFs selected";
  if (pdfFiles.length === 1) return pdfFiles[0].webkitRelativePath || pdfFiles[0].name;
  return `${pdfFiles.length} ${singularLabel}${pdfFiles.length === 1 ? "" : "s"} selected`;
}

async function checkExistingUploads(files) {
  const body = new FormData();
  for (const file of files) {
    body.append("pdfs", file, displayUploadName(file));
    body.append("pdf_relative_paths", uploadName(file));
  }
  appendSettings(body);
  const response = await fetch("/api/jobs/check-existing", { method: "POST", body });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Failed to check existing jobs.");
  }
  return response.json();
}

function buildUploadFormData(files, rerunExisting = false) {
  const body = new FormData();
  for (const file of files) {
    body.append("pdfs", file, displayUploadName(file));
    body.append("pdf_relative_paths", uploadName(file));
  }
  body.append("rerun_existing", rerunExisting ? "true" : "false");
  appendSettings(body);
  return body;
}

function buildSettingsFormData() {
  const body = new FormData();
  appendSettings(body);
  return body;
}

function appendSettings(body) {
  syncSystemPromptField();
  body.append("project_id", currentProjectId);
  const data = new FormData(form);
  for (const field of [
    "ocr_dpi",
    "ocr_batch_size",
    "deepseek_ocr_model_path",
    "rq_model_preset",
    "openai_api_key",
    "rq_prompt_filename",
    "rq_system_prompt",
  ]) {
    body.append(field, data.get(field) || "");
  }
  const isOpenAI = selectedPreset()?.settings?.provider === "openai";
  body.append("openai_input_mode", isOpenAI && openaiInputFileCheckbox?.checked ? "pdf_file" : "ocr_text");
}

function clearFileInputs() {
  pdfInput.value = "";
  folderInput.value = "";
  updateUploadSummaries();
}

function uploadName(file) {
  return file.webkitRelativePath || file.name;
}

function displayUploadName(file) {
  return file.name || uploadName(file).split("/").pop() || "uploaded.pdf";
}

function displayJobFilename(job) {
  const raw = typeof job === "string" ? job : job?.filename || job?.metadata?.original_filename || job?.job_id || "";
  return String(raw).split(/[\\/]/).pop() || raw || "Unknown file";
}

function askOverwriteDuplicates(duplicates) {
  const names = duplicates.map((item) => `${item.filename} (${item.prompt_filename || "prompt not recorded"} | ${item.model || "model not recorded"})`).slice(0, 8);
  if (duplicates.length > names.length) names.push(`...and ${duplicates.length - names.length} more`);
  return CEREBROUI.confirm({
    title: "Duplicate PDF decisions found",
    message: "Overwrite matching decisions and reuse existing OCR where possible? Choose Cancel to queue only new PDFs.",
    details: names,
    confirmLabel: "Overwrite duplicates",
  });
}

function startPolling() {
  schedulePdfPolling(0);
}

function startQueueRefresh() {
  schedulePdfPolling();
}

function schedulePdfPolling(delay = null) {
  window.clearTimeout(pollTimer);
  const hasActiveWork = pdfQueueHasActiveWork();
  const cadenceDelay = document.hidden ? 30000 : hasActiveWork ? 1500 : 15000;
  const nextDelay = delay ?? cadenceDelay;
  pollTimer = window.setTimeout(async () => {
    await restoreQueueFromJobList({ schedule: false });
    schedulePdfPolling();
  }, nextDelay);
  updatePollingLabel(hasActiveWork, cadenceDelay);
}

function pdfQueueHasActiveWork() {
  return Boolean(
    jobCounts.running ||
    jobCounts.queued ||
    queueState.current_job_id ||
    (queueState.current_job_ids || []).length ||
    queueState.pending_count ||
    queueState.openai_running_count ||
    queueState.openai_pending_count
  );
}

function updatePollingLabel(active, delay) {
  if (!autoRefreshStatus) return;
  currentPollingCadence = document.hidden
    ? `background checks every ${Math.round(delay / 1000)}s`
    : active
      ? `live updates every ${delay / 1000}s`
      : `idle checks every ${Math.round(delay / 1000)}s`;
  updateLastUpdatedDisplay();
}

function mergeJobRecords(records) {
  for (const record of records) {
    const existing = trackedJobs.get(record.job_id) || {};
    trackedJobs.set(record.job_id, normalizeJobRecord(record, existing));
  }
}

function normalizeJobRecord(record, existing = {}) {
  const status = record.status || {};
  const metadata = record.metadata || {};
  return {
    ...existing,
    job_id: record.job_id,
    filename: record.filename || metadata.original_filename || record.job_id,
    metadata,
    prompt_filename: metadata.rq_prompt_filename || record.prompt_filename || "",
    model: metadata.rq_screening_model || record.model || "",
    openai_input_mode: metadata.openai_input_mode || record.openai_input_mode || existing.openai_input_mode || "",
    created_at: metadata.created_at || record.created_at || existing.created_at || "",
    completed_at: metadata.completed_at || record.completed_at || existing.completed_at || "",
    job_dir: record.job_dir || existing.job_dir || "",
    ...status,
  };
}

async function restoreQueueFromJobList(options = {}) {
  try {
    await loadQueueState();
    await loadPdfJobWindow(jobWindow.offset >= 0 ? jobWindow.offset : 0, { force: true, render: false });
    markLastUpdated();
    renderQueue();
    const active = pickActiveJob();
    if (active) {
      currentJobId = active.job_id;
      setStages(active.stage);
    }
    if (jobCounts.all && !pdfSetupBody.classList.contains("setup-initialized")) {
      setPdfSetupCollapsed(true);
      pdfSetupBody.classList.add("setup-initialized");
    }
    if (options.schedule !== false) schedulePdfPolling();
  } catch (_error) {
    return;
  }
}

async function pollAllStatuses() {
  await restoreQueueFromJobList({ schedule: false });
  schedulePdfPolling();
}

function pickActiveJob() {
  const jobs = [...activeJobRecords, ...trackedJobs.values()];
  return (
    jobs.find((job) => job.status === "running") ||
    jobs.find((job) => job.status === "queued") ||
    jobs.find((job) => job.status === "failed") ||
    jobs.find((job) => job.status === "complete") ||
    null
  );
}

function countByStatus(status) {
  const key = status === "complete" ? "completed" : status;
  return Number(jobCounts[key] || 0);
}

async function loadPdfJobWindow(offset = pdfVisibleOffset(), options = {}) {
  const safeOffset = Math.max(0, Number(offset || 0));
  const key = `${safeOffset}:${activeStatusFilter}:${jobSearchQuery}`;
  if (!options.force && key === jobWindowRequestKey) return;
  if (!options.force && jobWindow.offset <= safeOffset && safeOffset < jobWindow.offset + Math.max(1, jobWindow.limit - 30)) return;
  jobWindowRequestKey = key;
  const params = new URLSearchParams({
    project_id: currentProjectId,
    offset: String(safeOffset),
    limit: String(JOB_LIST_LIMIT),
    status: activeStatusFilter,
    search: jobSearchQuery,
  });
  const response = await fetch(`/api/jobs?${params.toString()}`);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Could not load project jobs.");
  trackedJobs.clear();
  mergeJobRecords(payload.items || payload.jobs || []);
  jobWindow = {
    offset: Number(payload.offset || 0),
    limit: Number(payload.limit || JOB_LIST_LIMIT),
    total: Number(payload.total || 0),
    items: [...trackedJobs.values()],
  };
  jobCounts = { ...jobCounts, ...(payload.counts || {}) };
  activeJobRecords = (payload.active_items || []).map((record) => normalizeJobRecord(record));
  if (options.render !== false) renderQueue();
}

function pdfVisibleOffset() {
  return Math.max(0, Math.floor((queueList?.scrollTop || 0) / PDF_JOB_ROW_HEIGHT) - PDF_JOB_OVERSCAN);
}

function setPdfSetupCollapsed(collapsed) {
  pdfSetupBody?.classList.toggle("hidden", collapsed);
  togglePdfSetupButton?.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (togglePdfSetupButton) togglePdfSetupButton.textContent = collapsed ? "Configure new run" : "Hide setup";
}

function startLastUpdatedTimer() {
  updateLastUpdatedDisplay();
  if (lastUpdatedTimer) return;
  lastUpdatedTimer = window.setInterval(updateLastUpdatedDisplay, 5000);
}

function markLastUpdated() {
  lastSuccessfulRefreshAt = new Date();
  updateLastUpdatedDisplay();
}

function updateLastUpdatedDisplay() {
  if (!autoRefreshStatus) return;
  if (!lastSuccessfulRefreshAt) {
    autoRefreshStatus.textContent = `Auto-refreshing · ${currentPollingCadence}`;
    return;
  }
  const seconds = Math.max(0, Math.floor((Date.now() - lastSuccessfulRefreshAt.getTime()) / 1000));
  const relative = seconds < 5 ? "just now" : `${relativeSeconds(seconds)} ago`;
  autoRefreshStatus.textContent = `Auto-refreshing · ${currentPollingCadence} · Last updated ${relative}`;
}

function relativeSeconds(seconds) {
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h`;
}

function dashboardStatus(job) {
  if (!job) return "queued";
  if (job.stage === "error" || job.status === "failed" || job.status === "error") return "failed";
  if (job.status === "complete" || job.status === "completed") return "complete";
  if (activeJobIds().has(job.job_id) || job.stage === "openai_running") return "running";
  if (pendingJobIds().has(job.job_id) || job.stage === "openai_queued") return "queued";
  if (job.status === "running") return "running";
  if (job.status === "queued" || job.status === "pending") return "queued";
  return job.status || "queued";
}

function dashboardCounts() {
  return {
    total: Number(jobCounts.all || 0),
    complete: Number(jobCounts.completed || 0),
    running: Number(jobCounts.running || 0),
    queued: Number(jobCounts.queued || 0),
    failed: Number(jobCounts.failed || 0),
    other: 0,
  };
}

function filterStatusKey(job) {
  const status = dashboardStatus(job);
  if (status === "complete" || status === "completed") return "completed";
  if (status === "failed" || status === "error") return "failed";
  if (status === "running") return "running";
  if (status === "queued" || status === "pending") return "queued";
  return "queued";
}

function filterCounts() {
  return {
    all: Number(jobCounts.all || 0),
    running: Number(jobCounts.running || 0),
    queued: Number(jobCounts.queued || 0),
    completed: Number(jobCounts.completed || 0),
    failed: Number(jobCounts.failed || 0),
  };
}

function jobMatchesDashboardFilters(job) {
  if (activeStatusFilter !== "all" && filterStatusKey(job) !== activeStatusFilter) {
    return false;
  }
  const query = jobSearchQuery.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    displayJobFilename(job),
    job.filename || "",
    job.metadata?.original_filename || "",
    job.job_id || "",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function renderFilterControls(visibleCount) {
  const counts = filterCounts();
  for (const button of jobFilterButtons) {
    const key = button.dataset.jobFilter || "all";
    button.classList.toggle("active", key === activeStatusFilter);
    button.setAttribute("aria-pressed", key === activeStatusFilter ? "true" : "false");
    const count = button.querySelector("[data-filter-count]");
    if (count) count.textContent = counts[key] ?? 0;
  }
  if (clearJobSearchButton) {
    clearJobSearchButton.disabled = !jobSearchQuery.trim();
  }
  if (filterSummaryLine) {
    const searchText = jobSearchQuery.trim() ? ` matching "${jobSearchQuery.trim()}"` : "";
    const filterText = activeStatusFilter === "all" ? "all jobs" : `${activeStatusFilter} jobs`;
    filterSummaryLine.textContent = `${Number(visibleCount).toLocaleString()} ${filterText}${searchText}. Only visible rows are loaded.`;
  }
}

function updateDashboardControls() {
  if (!cleanQueueButton) return;
  const canClean = Boolean(queueState.paused);
  cleanQueueButton.disabled = !canClean;
  cleanQueueButton.title = canClean ? "Remove queued and pending jobs" : "Pause the queue before removing pending jobs";
  if (cleanQueueHint) {
    cleanQueueHint.textContent = canClean
      ? "Paused. You can remove queued/pending jobs; completed, failed, and running jobs are kept."
      : "Pause the queue before removing pending jobs.";
  }
}

function activeJobIds() {
  const ids = new Set();
  for (const id of queueState.current_job_ids || []) ids.add(id);
  if (queueState.current_job_id) ids.add(queueState.current_job_id);
  for (const id of queueState.openai_running_job_ids || []) ids.add(id);
  return ids;
}

function pendingJobIds() {
  const ids = new Set();
  for (const id of queueState.pending_job_ids || []) ids.add(id);
  for (const id of queueState.openai_pending_job_ids || []) ids.add(id);
  return ids;
}

function jobMode(job) {
  const metadata = job.metadata || {};
  const nestedSettings = metadata.settings && typeof metadata.settings === "object" ? metadata.settings : {};
  const inputMode = String(job.openai_input_mode || metadata.openai_input_mode || nestedSettings.openai_input_mode || "");
  const provider = String(metadata.rq_provider || nestedSettings.rq_provider || "");
  const model = String(job.model || metadata.rq_screening_model || nestedSettings.rq_screening_model || "");
  if (inputMode === "pdf_file" || metadata.openai_file_id) {
    return {
      label: "OpenAI file/source",
      detail: "PDF source pathway",
      className: "mode-openai-file",
      pathway: "openai-file",
    };
  }
  if (provider === "openai" || model.toLowerCase().startsWith("gpt-")) {
    return {
      label: "OCR/text",
      detail: "OpenAI model",
      className: "mode-openai-ocr",
      pathway: "ocr-text",
    };
  }
  return {
    label: "OCR/text",
    detail: "Local model",
    className: "mode-local",
    pathway: "ocr-text",
  };
}

function friendlyStage(job) {
  if (!job) return "Queued";
  if (job.stage === "error" || job.status === "failed") return "Failed";
  if (job.status === "complete") return "Complete";
  const labels = {
    queued: "Queued",
    upload: "Uploading PDF",
    render: "Rendering pages",
    find_deepseek: "Finding OCR model",
    ocr: "OCR running",
    merge: "Merging OCR text",
    prompt: "Building prompt",
    rq_model: "Loading model",
    rq_screening: "Model extraction",
    openai_queued: "OpenAI queued",
    openai_running: "OpenAI running",
    complete: "Complete",
  };
  return labels[job.stage] || sentenceCase(job.stage || job.status || "queued");
}

function statusBadgeLabel(job) {
  if (job.stage === "openai_queued") return "OpenAI queued";
  if (job.stage === "openai_running") return "OpenAI running";
  const labels = {
    complete: "Completed",
    running: "Running",
    queued: "Queued",
    failed: "Failed",
  };
  return labels[dashboardStatus(job)] || sentenceCase(dashboardStatus(job));
}

function sentenceCase(value) {
  const text = String(value || "").replaceAll("_", " ").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function pipelineSteps(job) {
  if (jobMode(job).pathway === "openai-file") {
    return [
      { key: "queued", label: "Queued", stages: ["queued"] },
      { key: "upload", label: "Uploading PDF", stages: ["upload", "prompt"] },
      { key: "openai_queued", label: "OpenAI queued", stages: ["openai_queued"] },
      { key: "openai_running", label: "OpenAI running", stages: ["openai_running", "rq_screening"] },
      { key: "complete", label: "Complete", stages: ["complete"] },
    ];
  }
  return [
    { key: "queued", label: "Queued", stages: ["queued"] },
    { key: "render", label: "Rendering pages", stages: ["upload", "render"] },
    { key: "ocr", label: "OCR running", stages: ["find_deepseek", "ocr"] },
    { key: "merge", label: "Merging OCR text", stages: ["merge"] },
    { key: "prompt", label: "Building prompt", stages: ["prompt"] },
    { key: "model", label: "Model extraction", stages: ["rq_model", "rq_screening", "openai_queued", "openai_running"] },
    { key: "complete", label: "Complete", stages: ["complete"] },
  ];
}

function renderPipeline(job) {
  const steps = pipelineSteps(job);
  const stage = job.status === "complete" ? "complete" : job.stage || job.status || "queued";
  let currentIndex = steps.findIndex((step) => step.stages.includes(stage));
  if (currentIndex === -1 && dashboardStatus(job) === "failed") {
    currentIndex = Math.max(0, steps.findIndex((step) => step.key === "complete") - 1);
  }
  return `
    <ol class="pathway-steps" aria-label="${escapeHtml(jobMode(job).label)} pathway">
      ${steps
        .map((step, index) => {
          const isComplete = dashboardStatus(job) === "complete" || (currentIndex !== -1 && index < currentIndex);
          const isActive = dashboardStatus(job) !== "complete" && currentIndex === index;
          const isFailed = dashboardStatus(job) === "failed" && currentIndex === index;
          const className = [isComplete ? "done" : "", isActive ? "active" : "", isFailed ? "failed" : ""]
            .filter(Boolean)
            .join(" ");
          return `<li class="${className}"><span></span>${escapeHtml(step.label)}</li>`;
        })
        .join("")}
    </ol>
  `;
}

function jobProgressValue(job) {
  const value = Number(job.progress);
  if (!Number.isFinite(value)) return null;
  return Math.max(0, Math.min(1, value));
}

function renderJobProgress(job) {
  const progress = jobProgressValue(job);
  if (progress === null) {
    return `<span class="progress-text">Progress not reported</span>`;
  }
  const percent = Math.round(progress * 100);
  return `
    <div class="mini-progress" aria-label="${percent}% complete">
      <span style="width: ${percent}%"></span>
    </div>
    <span class="progress-text">${percent}%</span>
  `;
}

function jobTimeText(job) {
  const metadata = job.metadata || {};
  const duration = Number(metadata.duration_seconds || job.duration_seconds);
  if (Number.isFinite(duration) && duration > 0) {
    return `Duration ${formatDuration(duration)}`;
  }
  const completedAt = metadata.completed_at || job.completed_at || "";
  if (completedAt) {
    return `Completed ${formatDate(completedAt)}`;
  }
  const createdAt = metadata.created_at || job.created_at || "";
  if (createdAt) {
    return `Queued ${formatDate(createdAt)}`;
  }
  return "";
}

function formatDuration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remaining}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function renderBatchDashboard() {
  const counts = dashboardCounts();
  renderBatchStats(counts);
  renderActiveJobs();
  renderTechnicalEvents();
  updateBatchStatus(counts);
  updateDashboardControls();
}

function renderBatchStats(counts) {
  if (!batchStats) return;
  const ocrRunning = (queueState.current_job_ids || []).length || (queueState.current_job_id ? 1 : 0);
  const ocrMax = queueState.max_ocr_workers || 0;
  const openaiRunning = queueState.openai_running_count || (queueState.openai_running_job_ids || []).length || 0;
  const openaiMax = queueState.max_openai_concurrent_requests || 0;
  const metrics = [
    { label: "Total files", value: counts.total, tone: "" },
    { label: "Completed", value: counts.complete, tone: "complete" },
    { label: "Running", value: counts.running, tone: "running" },
    { label: "Queued", value: counts.queued, tone: "queued" },
    { label: "Failed", value: counts.failed, tone: "failed" },
    {
      label: "Active workers",
      value: `${ocrRunning + openaiRunning}`,
      detail: `OpenAI ${openaiRunning}/${openaiMax || "-"} | OCR ${ocrRunning}/${ocrMax || "-"}`,
      tone: "workers",
    },
  ];
  batchStats.innerHTML = metrics
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
  if (activeWorkersBadge) {
    activeWorkersBadge.textContent =
      ocrRunning || openaiRunning
        ? `OpenAI workers: ${openaiRunning} / ${openaiMax || "-"} active | OCR workers: ${ocrRunning} / ${ocrMax || "-"} active`
        : "No active workers";
  }
}

function updateBatchStatus(counts) {
  if (!counts.total) {
    progressBar.style.width = "0%";
    statusLine.textContent = "Waiting for upload.";
    if (batchSummaryLine) batchSummaryLine.textContent = "No files are currently being tracked.";
    jobBadge.textContent = "No job";
    jobBadge.className = "badge";
    setStages("");
    return;
  }
  const percent = Math.round((counts.complete / counts.total) * 100);
  progressBar.style.width = `${percent}%`;
  const activeText = counts.running
    ? `${counts.running} running`
    : counts.queued
      ? `${counts.queued} queued`
      : "no active jobs";
  statusLine.textContent = `${counts.complete} of ${counts.total} files completed. ${activeText}.${counts.failed ? ` ${counts.failed} failed.` : ""}`;
  if (batchSummaryLine) {
    batchSummaryLine.textContent = counts.total === 1 ? "Single-file run" : `Batch run with ${counts.total} files`;
  }
  jobBadge.textContent = `${counts.complete} / ${counts.total} complete`;
  jobBadge.className = `badge ${counts.failed ? "failed" : counts.complete === counts.total ? "complete" : counts.running ? "running" : "queued"}`;
}

function renderActiveJobs() {
  if (!activeJobsList || !activeJobsPanel) return;
  const activeIds = activeJobIds();
  const activeJobs = activeJobRecords.filter((job) => activeIds.has(job.job_id) || ["running", "queued"].includes(dashboardStatus(job)));
  if (!activeJobs.length) {
    activeJobsList.innerHTML = `
      <div class="empty-state">
        <strong>No active files right now.</strong>
        <span>Queued files will appear here when an OCR worker or OpenAI worker starts them.</span>
      </div>
    `;
    return;
  }
  activeJobsList.innerHTML = activeJobs
    .map((job) => {
      const mode = jobMode(job);
      const timeText = jobTimeText(job);
      return `
        <article class="active-job-card ${mode.className}">
          <div class="active-job-head">
            <div>
              <span class="mode-badge ${mode.className}">${escapeHtml(mode.label)}</span>
              <h4>${escapeHtml(displayJobFilename(job))}</h4>
            </div>
            <span class="status-badge ${cssToken(dashboardStatus(job))}">${escapeHtml(statusBadgeLabel(job))}</span>
          </div>
          <p>${escapeHtml(job.message || friendlyStage(job))}</p>
          <div class="active-job-meta">
            <span>${escapeHtml(mode.detail)}</span>
            <span>${escapeHtml(friendlyStage(job))}</span>
            ${timeText ? `<span>${escapeHtml(timeText)}</span>` : ""}
          </div>
          <div class="job-progress">${renderJobProgress(job)}</div>
          ${renderPipeline(job)}
        </article>
      `;
    })
    .join("");
}

function renderTechnicalEvents() {
  if (!technicalEventsList) return;
  const active = pickActiveJob();
  if (!active) {
    technicalEventsList.innerHTML = `<p class="technical-empty">No processing events have been received yet.</p>`;
    return;
  }
  const events = [...(active.events || [])].slice(-10).reverse();
  const eventItems = events.length
    ? events
        .map((event) => {
          const name = event.event || event.stage || "event";
          const details = { ...event };
          delete details.event;
          const detailText = Object.keys(details).length ? JSON.stringify(details) : "";
          return `
            <div class="technical-event">
              <strong>${escapeHtml(name)}</strong>
              ${detailText ? `<code>${escapeHtml(detailText)}</code>` : ""}
            </div>
          `;
        })
        .join("")
    : `<p class="technical-empty">No detailed events are recorded for this job yet.</p>`;
  technicalEventsList.innerHTML = `
    <div class="technical-event-head">
      <span>${escapeHtml(displayJobFilename(active))}</span>
      <code>${escapeHtml(active.stage || active.status || "")}</code>
    </div>
    ${eventItems}
  `;
}

function cssToken(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function orderedJobsForRender() {
  const jobs = [...trackedJobs.values()];
  const byId = new Map(jobs.map((job) => [job.job_id, job]));
  const childrenBySource = new Map();
  const childIds = new Set();
  for (const job of jobs) {
    const sourceId = job.metadata?.rerun_created_from_job_id || job.rerun_created_from_job_id || "";
    if (!sourceId || sourceId === job.job_id || !byId.has(sourceId)) {
      continue;
    }
    childIds.add(job.job_id);
    if (!childrenBySource.has(sourceId)) {
      childrenBySource.set(sourceId, []);
    }
    childrenBySource.get(sourceId).push(job);
  }

  const ordered = [];
  const emitted = new Set();
  function addWithChildren(job) {
    if (!job || emitted.has(job.job_id)) return;
    emitted.add(job.job_id);
    ordered.push(job);
    for (const child of childrenBySource.get(job.job_id) || []) {
      addWithChildren(child);
    }
  }

  for (const job of jobs) {
    if (!childIds.has(job.job_id)) {
      addWithChildren(job);
    }
  }
  for (const job of jobs) {
    addWithChildren(job);
  }
  return ordered;
}

function renderQueue() {
  renderBatchDashboard();
  queuePanel.classList.remove("hidden");
  const ocrPending = queueState.pending_count || 0;
  const openaiPending = queueState.openai_pending_count || 0;
  const openaiRunning = queueState.openai_running_count || 0;
  const ocrRunning = (queueState.current_job_ids || []).length || (queueState.current_job_id ? 1 : 0);
  queueSummary.innerHTML = `
    <span>${queueState.paused ? "Shared PDF queue paused" : "Shared PDF queue running"}</span>
    <span>OCR/local: ${escapeHtml(ocrRunning)} running, ${escapeHtml(ocrPending)} queued</span>
    <span>OpenAI: ${escapeHtml(openaiRunning)} running, ${escapeHtml(openaiPending)} queued</span>
  `;
  renderFilterControls(jobWindow.total);
  pdfJobTableShell?.setAttribute("aria-rowcount", String(jobWindow.total));
  pdfJobVirtualSpacer.style.height = `${Math.max(1, jobWindow.total) * PDF_JOB_ROW_HEIGHT}px`;
  pdfJobVirtualRows.innerHTML = "";
  if (!jobWindow.total) {
    pdfJobVirtualSpacer.style.height = "160px";
    pdfJobVirtualRows.innerHTML = `
      <div class="pdf-job-empty">
        <strong>${jobCounts.all ? "No jobs match the current filters." : "No project jobs yet."}</strong>
        <span>${jobCounts.all ? "Adjust the status filter or filename search." : "Upload PDFs to create the first extraction run."}</span>
      </div>
    `;
    return;
  }
  jobWindow.items.forEach((job, index) => {
    const rowIndex = jobWindow.offset + index;
    const row = document.createElement("div");
    const status = dashboardStatus(job);
    const isActive = status === "queued" || status === "running";
    const promptName = job.prompt_filename || job.metadata?.rq_prompt_filename || "";
    const modelName = job.model || job.metadata?.rq_screening_model || "";
    const timeText = jobTimeText(job);
    row.className = `pdf-job-data-row ${cssToken(status)}`;
    row.style.transform = `translateY(${rowIndex * PDF_JOB_ROW_HEIGHT}px)`;
    row.setAttribute("role", "row");
    row.innerHTML = `
      <div class="pdf-job-cell pdf-job-file" role="gridcell" title="${escapeAttribute(displayJobFilename(job))}">
        <strong>${escapeHtml(displayJobFilename(job))}</strong>
        <small>${escapeHtml(job.job_id)}</small>
      </div>
      <div class="pdf-job-cell pdf-job-status" role="gridcell">
        <span class="status-badge ${cssToken(status)}">${escapeHtml(statusBadgeLabel(job))}</span>
        <small title="${escapeAttribute(job.message || friendlyStage(job))}">${escapeHtml(friendlyStage(job))}</small>
      </div>
      <div class="pdf-job-cell pdf-job-model" role="gridcell" title="${escapeAttribute([modelName, promptName].filter(Boolean).join(" | "))}">
        <strong>${escapeHtml(modelName || "Model not recorded")}</strong>
        <small>${escapeHtml(promptName || "Prompt not recorded")}</small>
      </div>
      <div class="pdf-job-cell pdf-job-time" role="gridcell"><span>${escapeHtml(timeText || "Not started")}</span></div>
      <div class="pdf-job-cell queue-row-actions" role="gridcell">
        <button type="button" data-action="view" ${status === "complete" ? "" : "disabled"}>View</button>
        <button type="button" data-action="rerun" ${isActive ? "disabled" : ""}>Rerun</button>
        <button type="button" data-action="delete" ${isActive ? "disabled" : ""}>Delete</button>
      </div>
    `;
    row.querySelector("[data-action='view']").addEventListener("click", (event) => showPdfResultInspector(job, event.currentTarget));
    row.querySelector("[data-action='rerun']").addEventListener("click", async () => {
      await rerunJob(job);
    });
    row.querySelector("[data-action='delete']").addEventListener("click", async () => {
      await deleteJob(job);
    });
    pdfJobVirtualRows.appendChild(row);
  });
}

async function showPdfResultInspector(job, trigger) {
  const inspector = CEREBROUI.openInspector({
    kicker: "PDF extraction result",
    title: displayJobFilename(job),
    subtitle: job.job_id,
    trigger,
  });
  try {
    const response = await fetch(withProject(`/api/jobs/${encodeURIComponent(job.job_id)}/result`));
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "Result is not available.");
    const metadata = payload.metadata || {};
    const output = payload.output || "";
    inspector.setContent(`
      <div class="inspector-actions">
        <button type="button" data-inspector-copy>Copy result</button>
        <a class="button" href="${withProject(`/api/jobs/${encodeURIComponent(job.job_id)}/download`)}">Download .md</a>
      </div>
      <dl class="metadata-list compact">
        <div><dt>Model</dt><dd>${escapeHtml(metadata.rq_screening_model || "")}</dd></div>
        <div><dt>Prompt</dt><dd>${escapeHtml(metadata.rq_prompt_filename || "")}</dd></div>
        <div><dt>Pages</dt><dd>${escapeHtml(metadata.number_of_pages || "")}</dd></div>
        <div><dt>Warnings</dt><dd>${escapeHtml((metadata.warnings || []).join("; ") || "None")}</dd></div>
      </dl>
      <textarea class="inspector-result-text" spellcheck="false" readonly>${escapeHtml(output)}</textarea>
      <details><summary>Processing stages and OCR text</summary><pre>${escapeHtml(payload.merged_full_text || "")}</pre></details>
      <details><summary>Prompt sent to model</summary><pre>${escapeHtml(payload.prompt || "")}</pre></details>
      <details><summary>Metadata</summary><pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre></details>
    `);
    inspector.body.querySelector("[data-inspector-copy]")?.addEventListener("click", async (event) => {
      await navigator.clipboard.writeText(output);
      event.currentTarget.textContent = "Copied";
    });
  } catch (error) {
    inspector.setContent(`<p class="queue-error">${escapeHtml(error.message || "Could not load result.")}</p>`);
  }
}

async function rerunJob(job) {
  const response = await fetch(`/api/jobs/${job.job_id}/rerun`, { method: "POST", body: buildSettingsFormData() });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || `Could not rerun ${job.filename || job.job_id}.`, 1, "failed");
    return;
  }
  const queuedJob = payload.job || null;
  mergeJobRecords(queuedJob ? [queuedJob] : []);
  if (payload.created_new_job) {
    const promptName = payload.prompt_filename || queuedJob?.metadata?.rq_prompt_filename || "";
    const modelName = payload.model || queuedJob?.metadata?.rq_screening_model || "";
    setStatus(
      `${job.filename || job.job_id}: queued as a new run${promptName || modelName ? ` (${[promptName, modelName].filter(Boolean).join(" | ")})` : ""}`,
      0,
      "queued"
    );
  } else {
    setStatus(`${job.filename || job.job_id}: queued for screening rerun`, 0, "queued");
  }
  resultPanel.classList.add("hidden");
  renderQueue();
  startPolling();
  await pollAllStatuses();
}

async function deleteJob(job) {
  const confirmed = await CEREBROUI.confirm({
    title: "Delete PDF job",
    message: `Delete ${displayJobFilename(job)} and its complete job folder?`,
    details: ["The extracted output, OCR text, prompt transcript, and metadata will be removed."],
    confirmLabel: "Delete job",
    danger: true,
  });
  if (!confirmed) {
    return;
  }
  const response = await fetch(withProject(`/api/jobs/${job.job_id}`), { method: "DELETE" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || `Could not delete ${job.filename || job.job_id}.`, 1, "failed");
    return;
  }
  trackedJobs.delete(job.job_id);
  if (currentJobId === job.job_id) {
    currentJobId = null;
  }
  setStatus(`${job.filename || job.job_id}: deleted`, 0, "queued");
  await restoreQueueFromJobList();
}

async function loadQueueState() {
  try {
    const response = await fetch(withProject("/api/queue"));
    if (!response.ok) return;
    queueState = await response.json();
  } catch (_error) {
    return;
  }
}

async function loadResult(jobId) {
  const response = await fetch(withProject(`/api/jobs/${jobId}/result`));
  const payload = await response.json();
  const metadata = payload.metadata || {};
  resultText.value = payload.output || "";
  mergedText.textContent = payload.merged_full_text || "";
  promptText.textContent = payload.prompt || "";
  metadataText.textContent = JSON.stringify(metadata, null, 2);
  document.querySelector("#pdfName").textContent = metadata.original_filename || "";
  document.querySelector("#pageCount").textContent = metadata.number_of_pages || "";
  document.querySelector("#deepseekPath").textContent = metadata.detected_deepseek_ocr_model_path || "";
  document.querySelector("#warnings").textContent = (metadata.warnings || []).join("; ") || "None";
  downloadLink.href = withProject(`/api/jobs/${jobId}/download`);
  resultPanel.classList.remove("hidden");
}

function setStatus(message, progress, status) {
  statusLine.textContent = message;
  progressBar.style.width = `${Math.round(progress * 100)}%`;
  jobBadge.className = `badge ${status}`;
}

function setStages(stage) {
  document.querySelectorAll("#stageList li").forEach((item) => {
    item.classList.toggle("active", item.dataset.stage === stage);
    item.classList.toggle("done", stageOrder(item.dataset.stage) < stageOrder(stage));
  });
}

function stageOrder(stage) {
  const stages = [
    "queued",
    "upload",
    "render",
    "find_deepseek",
    "ocr",
    "merge",
    "prompt",
    "rq_model",
    "rq_screening",
    "openai_queued",
    "openai_running",
    "complete",
  ];
  const index = stages.indexOf(stage);
  return index === -1 ? -1 : index;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
