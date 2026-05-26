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
const modelPresets = JSON.parse(document.querySelector("#modelPresetData")?.textContent || "[]");
const JOB_LIST_LIMIT = 0;

let pollTimer = null;
let refreshTimer = null;
let currentJobId = null;
let trackedJobs = new Map();
let expandedJobIds = new Set();
let inlineResultCache = new Map();
let queueState = { paused: false, current_job_id: null, pending_job_ids: [], pending_count: 0 };
let activeStatusFilter = "all";
let jobSearchQuery = "";
let lastSuccessfulRefreshAt = null;
let lastUpdatedTimer = null;

document.addEventListener("DOMContentLoaded", () => {
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
  button.addEventListener("click", () => {
    activeStatusFilter = button.dataset.jobFilter || "all";
    renderQueue();
  });
}

if (jobSearchInput) {
  jobSearchInput.addEventListener("input", () => {
    jobSearchQuery = jobSearchInput.value || "";
    renderQueue();
  });
}

if (clearJobSearchButton) {
  clearJobSearchButton.addEventListener("click", () => {
    jobSearchQuery = "";
    if (jobSearchInput) jobSearchInput.value = "";
    renderQueue();
    jobSearchInput?.focus();
  });
}

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
  pauseButton.disabled = true;
  try {
    const response = await fetch("/api/queue/pause", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) queueState = payload;
    setStatus("Queue paused. Active worker is being interrupted.", 0, "queued");
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
    const response = await fetch("/api/queue/resume", { method: "POST", body: buildSettingsFormData() });
    const payload = await response.json().catch(() => ({}));
    if (response.ok) queueState = payload;
    setStatus("Queue resumed with the selected model preset.", 0, "running");
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
    const response = await fetch("/api/queue/retry-failed", { method: "POST" });
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
  if (!window.confirm("Remove all queued jobs from the queue and jobs list? Completed and failed jobs will be kept.")) {
    return;
  }
  cleanQueueButton.disabled = true;
  try {
    const response = await fetch("/api/queue/clean", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    setStatus(`Removed ${payload.removed || 0} queued job${payload.removed === 1 ? "" : "s"} from the queue.`, 0, "queued");
    await restoreQueueFromJobList();
    startPolling();
  } finally {
    updateDashboardControls();
  }
});

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
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    const names = duplicates.map((item) => `${item.filename}\n${item.prompt_filename || ""} | ${item.model || ""}`).slice(0, 8);
    const extra = duplicates.length > names.length ? `\n...and ${duplicates.length - names.length} more` : "";
    overlay.innerHTML = `
      <div class="modal">
        <p>These PDFs already have decisions with the same prompt and model.</p>
        <pre>${escapeHtml(names.join("\n\n") + extra)}</pre>
        <p>Overwrite decisions and reuse OCR?</p>
        <div class="modal-actions">
          <button type="button" data-answer="yes">Yes</button>
          <button type="button" data-answer="no">No</button>
        </div>
      </div>
    `;
    overlay.querySelector("[data-answer='yes']").addEventListener("click", () => {
      overlay.remove();
      resolve(true);
    });
    overlay.querySelector("[data-answer='no']").addEventListener("click", () => {
      overlay.remove();
      resolve(false);
    });
    document.body.appendChild(overlay);
  });
}

function startPolling() {
  if (pollTimer) return;
  pollAllStatuses();
  pollTimer = window.setInterval(pollAllStatuses, 1500);
}

function startQueueRefresh() {
  if (refreshTimer) return;
  refreshTimer = window.setInterval(restoreQueueFromJobList, 10000);
}

function mergeJobRecords(records) {
  for (const record of records) {
    const existing = trackedJobs.get(record.job_id) || {};
    const status = record.status || {};
    const metadata = record.metadata || {};
    trackedJobs.set(record.job_id, {
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
    });
  }
}

async function restoreQueueFromJobList() {
  try {
    await loadQueueState();
    const response = await fetch(`/api/jobs?limit=${JOB_LIST_LIMIT}`);
    if (!response.ok) return;
    const payload = await response.json();
    trackedJobs.clear();
    mergeJobRecords((payload.jobs || []).reverse());
    markLastUpdated();
    renderQueue();
    const active = pickActiveJob();
    if (active) {
      currentJobId = active.job_id;
      setStages(active.stage);
    }
    if ([...trackedJobs.values()].some((job) => job.status === "queued" || job.status === "running")) {
      startPolling();
    }
    startQueueRefresh();
  } catch (_error) {
    return;
  }
}

async function pollAllStatuses() {
  if (!trackedJobs.size) return;
  await loadQueueState();
  const entries = [...trackedJobs.values()].filter((job) => job.status === "queued" || job.status === "running");
  await Promise.all(
    entries.map(async (job) => {
      try {
        const response = await fetch(`/api/jobs/${job.job_id}/status`);
        if (!response.ok) return;
        const status = await response.json();
        trackedJobs.set(job.job_id, { ...job, ...status });
      } catch (_error) {
        return;
      }
    })
  );

  renderQueue();
  markLastUpdated();
  const active = pickActiveJob();
  if (active) {
    currentJobId = active.job_id;
    setStages(active.stage);
  }

  const allDone = [...trackedJobs.values()].every((job) => job.status === "complete" || job.status === "failed");
  if (allDone) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function pickActiveJob() {
  const jobs = [...trackedJobs.values()];
  return (
    jobs.find((job) => job.status === "running") ||
    jobs.find((job) => job.status === "queued") ||
    jobs.find((job) => job.status === "failed") ||
    jobs.find((job) => job.status === "complete") ||
    null
  );
}

function countByStatus(status) {
  return [...trackedJobs.values()].filter((job) => job.status === status).length;
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
    autoRefreshStatus.textContent = "Auto-refreshing · Waiting for first update";
    return;
  }
  const seconds = Math.max(0, Math.floor((Date.now() - lastSuccessfulRefreshAt.getTime()) / 1000));
  const relative = seconds < 5 ? "just now" : `${relativeSeconds(seconds)} ago`;
  autoRefreshStatus.textContent = `Auto-refreshing · Last updated ${relative}`;
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
  const counts = { total: trackedJobs.size, complete: 0, running: 0, queued: 0, failed: 0, other: 0 };
  for (const job of trackedJobs.values()) {
    const status = dashboardStatus(job);
    if (Object.prototype.hasOwnProperty.call(counts, status)) {
      counts[status] += 1;
    } else {
      counts.other += 1;
    }
  }
  return counts;
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
  const counts = { all: trackedJobs.size, running: 0, queued: 0, completed: 0, failed: 0 };
  for (const job of trackedJobs.values()) {
    const key = filterStatusKey(job);
    if (Object.prototype.hasOwnProperty.call(counts, key)) {
      counts[key] += 1;
    }
  }
  return counts;
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
    filterSummaryLine.textContent = `Showing ${visibleCount} of ${counts.all} ${filterText}${searchText}.`;
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
  const activeJobs = orderedJobsForRender().filter((job) => activeIds.has(job.job_id) || dashboardStatus(job) === "running");
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
  const viewState = captureInlineViewState();
  const pageScroll = { x: window.scrollX, y: window.scrollY };
  renderBatchDashboard();
  if (!trackedJobs.size) {
    queuePanel.classList.remove("hidden");
    renderFilterControls(0);
    queueList.innerHTML = `
      <div class="empty-state">
        <strong>No files in the queue.</strong>
        <span>Upload PDFs and add them to the queue to start tracking batch progress.</span>
      </div>
    `;
    return;
  }
  queuePanel.classList.remove("hidden");
  queueList.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "queue-summary cockpit-summary";
  const ocrPending = queueState.pending_count || 0;
  const openaiPending = queueState.openai_pending_count || 0;
  const openaiRunning = queueState.openai_running_count || 0;
  const ocrRunning = (queueState.current_job_ids || []).length || (queueState.current_job_id ? 1 : 0);
  summary.innerHTML = `
    <span>${queueState.paused ? "Queue paused" : "Queue running"}</span>
    <span>OCR/local: ${escapeHtml(ocrRunning)} running, ${escapeHtml(ocrPending)} queued</span>
    <span>OpenAI: ${escapeHtml(openaiRunning)} running, ${escapeHtml(openaiPending)} queued</span>
  `;
  queueList.appendChild(summary);
  const jobsToRender = orderedJobsForRender().filter(jobMatchesDashboardFilters);
  renderFilterControls(jobsToRender.length);
  if (!jobsToRender.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = `
      <strong>No jobs match the current filters.</strong>
      <span>Adjust the status filter or filename search to broaden the list.</span>
    `;
    queueList.appendChild(empty);
  }
  for (const job of jobsToRender) {
    const row = document.createElement("div");
    const status = dashboardStatus(job);
    const isActive = status === "queued" || status === "running";
    const promptName = job.prompt_filename || job.metadata?.rq_prompt_filename || "";
    const modelName = job.model || job.metadata?.rq_screening_model || "";
    const mode = jobMode(job);
    const timeText = jobTimeText(job);
    const errorText = status === "failed" ? job.error || job.message || "" : "";
    row.className = `queue-row file-job-card ${cssToken(status)} ${mode.className}`;
    row.innerHTML = `
      <div class="queue-file">
        <div class="queue-file-title">${escapeHtml(displayJobFilename(job))}</div>
        <div class="queue-file-meta">${escapeHtml([promptName, modelName].filter(Boolean).join(" | "))}</div>
        ${timeText ? `<div class="queue-file-meta">${escapeHtml(timeText)}</div>` : ""}
      </div>
      <div class="queue-route">
        <span class="mode-badge ${mode.className}">${escapeHtml(mode.label)}</span>
        <small>${escapeHtml(mode.detail)}</small>
      </div>
      <div class="queue-stage">
        <span class="status-badge ${cssToken(status)}">${escapeHtml(statusBadgeLabel(job))}</span>
        <strong>${escapeHtml(friendlyStage(job))}</strong>
        <p>${escapeHtml(job.message || "")}</p>
        <div class="job-progress">${renderJobProgress(job)}</div>
      </div>
      <div class="queue-pathway">${renderPipeline(job)}</div>
      ${errorText ? `<div class="queue-error">${escapeHtml(errorText)}</div>` : ""}
      <div class="queue-row-actions">
        <button type="button" data-action="view" ${status === "complete" ? "" : "disabled"}>${expandedJobIds.has(job.job_id) ? "Hide" : "View"}</button>
        <button type="button" data-action="rerun" ${isActive ? "disabled" : ""}>Rerun</button>
        <button type="button" data-action="delete" ${isActive ? "disabled" : ""}>Delete</button>
      </div>
    `;
    row.querySelector("[data-action='view']").addEventListener("click", async () => {
      await toggleInlineResult(job);
    });
    row.querySelector("[data-action='rerun']").addEventListener("click", async () => {
      await rerunJob(job);
    });
    row.querySelector("[data-action='delete']").addEventListener("click", async () => {
      await deleteJob(job);
    });
    queueList.appendChild(row);
    if (expandedJobIds.has(job.job_id)) {
      queueList.appendChild(renderInlineResult(job));
    }
  }
  restoreInlineViewState(viewState);
  window.requestAnimationFrame(() => window.scrollTo(pageScroll.x, pageScroll.y));
}

async function toggleInlineResult(job) {
  currentJobId = job.job_id;
  resultPanel.classList.add("hidden");
  if (expandedJobIds.has(job.job_id)) {
    expandedJobIds.delete(job.job_id);
    renderQueue();
    return;
  }
  expandedJobIds.add(job.job_id);
  if (!inlineResultCache.has(job.job_id)) {
    inlineResultCache.set(job.job_id, { loading: true });
    renderQueue();
    await fetchInlineResult(job.job_id);
  }
  renderQueue();
}

async function fetchInlineResult(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}/result`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "Result is not available.");
    }
    inlineResultCache.set(jobId, { loading: false, payload });
  } catch (error) {
    inlineResultCache.set(jobId, { loading: false, error: error.message || "Could not load result." });
  }
}

function renderInlineResult(job) {
  const panel = document.createElement("div");
  panel.className = "inline-result";
  panel.dataset.jobId = job.job_id;
  const cached = inlineResultCache.get(job.job_id);
  if (!cached || cached.loading) {
    panel.innerHTML = `<p class="inline-result-status">Loading result...</p>`;
    return panel;
  }
  if (cached.error) {
    panel.innerHTML = `<p class="inline-result-status error">${escapeHtml(cached.error)}</p>`;
    return panel;
  }

  const payload = cached.payload || {};
  const metadata = payload.metadata || {};
  const output = payload.output || "";
  panel.innerHTML = `
    <div class="inline-result-head">
      <div>
        <h3>Result</h3>
        <p>${escapeHtml(displayJobFilename(metadata.original_filename || job.filename || job.job_id))}</p>
      </div>
      <div class="actions">
        <button type="button" data-action="copy-inline">Copy result</button>
        <a class="button" href="/api/jobs/${encodeURIComponent(job.job_id)}/download">Download .md</a>
      </div>
    </div>
    <dl class="metadata-list compact inline-metadata">
      <div><dt>Job</dt><dd>${escapeHtml(job.job_id)}</dd></div>
      <div><dt>Model</dt><dd>${escapeHtml(metadata.rq_screening_model || "")}</dd></div>
      <div><dt>Pages</dt><dd>${escapeHtml(metadata.number_of_pages || "")}</dd></div>
      <div><dt>Warnings</dt><dd>${escapeHtml((metadata.warnings || []).join("; ") || "None")}</dd></div>
    </dl>
    <textarea class="inline-result-text" spellcheck="false" readonly>${escapeHtml(output)}</textarea>
    <details>
      <summary>View merged OCR text</summary>
      <pre>${escapeHtml(payload.merged_full_text || "")}</pre>
    </details>
    <details>
      <summary>View prompt sent to model</summary>
      <pre>${escapeHtml(payload.prompt || "")}</pre>
    </details>
    <details>
      <summary>View metadata</summary>
      <pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre>
    </details>
  `;
  panel.querySelector("[data-action='copy-inline']").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    await navigator.clipboard.writeText(output);
    button.textContent = "Copied";
    window.setTimeout(() => {
      button.textContent = "Copy result";
    }, 1200);
  });
  return panel;
}

function captureInlineViewState() {
  const state = new Map();
  document.querySelectorAll(".inline-result[data-job-id]").forEach((panel) => {
    const jobId = panel.dataset.jobId;
    if (!jobId) return;
    const textarea = panel.querySelector(".inline-result-text");
    const details = [...panel.querySelectorAll("details")];
    const preBlocks = [...panel.querySelectorAll("pre")];
    state.set(jobId, {
      textScrollTop: textarea ? textarea.scrollTop : 0,
      detailOpen: details.map((item) => item.open),
      preScrollTop: preBlocks.map((item) => item.scrollTop),
    });
  });
  return state;
}

function restoreInlineViewState(state) {
  document.querySelectorAll(".inline-result[data-job-id]").forEach((panel) => {
    const jobId = panel.dataset.jobId;
    const saved = state.get(jobId);
    if (!saved) return;
    const textarea = panel.querySelector(".inline-result-text");
    if (textarea) {
      textarea.scrollTop = saved.textScrollTop || 0;
    }
    [...panel.querySelectorAll("details")].forEach((item, index) => {
      item.open = Boolean(saved.detailOpen?.[index]);
    });
    [...panel.querySelectorAll("pre")].forEach((item, index) => {
      item.scrollTop = saved.preScrollTop?.[index] || 0;
    });
  });
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
    expandedJobIds.delete(job.job_id);
    inlineResultCache.delete(job.job_id);
    setStatus(`${job.filename || job.job_id}: queued for screening rerun`, 0, "queued");
  }
  resultPanel.classList.add("hidden");
  renderQueue();
  startPolling();
  await pollAllStatuses();
}

async function deleteJob(job) {
  if (!window.confirm(`Delete ${job.filename || job.job_id} and its whole job folder?`)) {
    return;
  }
  const response = await fetch(`/api/jobs/${job.job_id}`, { method: "DELETE" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    setStatus(payload.detail || `Could not delete ${job.filename || job.job_id}.`, 1, "failed");
    return;
  }
  trackedJobs.delete(job.job_id);
  expandedJobIds.delete(job.job_id);
  inlineResultCache.delete(job.job_id);
  if (currentJobId === job.job_id) {
    currentJobId = null;
  }
  setStatus(`${job.filename || job.job_id}: deleted`, 0, "queued");
  await restoreQueueFromJobList();
}

async function loadQueueState() {
  try {
    const response = await fetch("/api/queue");
    if (!response.ok) return;
    queueState = await response.json();
  } catch (_error) {
    return;
  }
}

async function loadResult(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/result`);
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
  downloadLink.href = `/api/jobs/${jobId}/download`;
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
