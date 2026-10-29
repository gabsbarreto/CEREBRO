const projectRows = Array.from(document.querySelectorAll("#projectsTableBody tr"));
const activeTab = document.querySelector("#activeProjectsTab");
const archivedTab = document.querySelector("#archivedProjectsTab");
const archiveButton = document.querySelector("#archiveProjectButton");
const deleteButton = document.querySelector("#deleteProjectButton");
const statusMessage = document.querySelector("#projectActionStatus");
const projectTableBody = document.querySelector("#projectsTableBody");
const sortButtons = Array.from(document.querySelectorAll(".project-sort"));
const nameCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
let showingArchived = false;
let sortColumn = "name";
let sortDirection = "ascending";

document.querySelectorAll("time[data-date]").forEach((element) => {
  const value = element.dataset.date;
  const date = new Date(value);
  if (value && !Number.isNaN(date.getTime())) {
    element.textContent = date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    element.dateTime = value;
  }
});

function selectedRow() {
  return projectRows.find((row) => !row.hidden && row.querySelector('input[type="radio"]').checked);
}

function projectName(row) {
  return row.querySelector(".project-name-link").textContent.trim();
}

function projectDate(row, column) {
  const time = row.querySelectorAll("time[data-date]")[column === "created" ? 0 : 1];
  const value = time.dataset.date;
  const timestamp = value ? Date.parse(value) : NaN;
  return Number.isFinite(timestamp) ? timestamp : null;
}

function sortProjects() {
  const direction = sortDirection === "ascending" ? 1 : -1;
  projectRows.sort((left, right) => {
    if (sortColumn !== "name") {
      const leftDate = projectDate(left, sortColumn);
      const rightDate = projectDate(right, sortColumn);
      if (leftDate === null && rightDate !== null) return 1;
      if (rightDate === null && leftDate !== null) return -1;
      if (leftDate !== null && rightDate !== null && leftDate !== rightDate) return direction * (leftDate - rightDate);
    }
    return nameCollator.compare(projectName(left), projectName(right)) * (sortColumn === "name" ? direction : 1);
  });
  projectRows.forEach((row) => projectTableBody.appendChild(row));
  sortButtons.forEach((button) => {
    const active = button.dataset.sort === sortColumn;
    if (active) button.closest("th").setAttribute("aria-sort", sortDirection);
    else button.closest("th").removeAttribute("aria-sort");
    button.querySelector(".project-sort-indicator").textContent = active ? (sortDirection === "ascending" ? "\u25b2" : "\u25bc") : "";
  });
}

sortButtons.forEach((button) => button.addEventListener("click", () => {
  const column = button.dataset.sort;
  sortDirection = column === sortColumn
    ? (sortDirection === "ascending" ? "descending" : "ascending")
    : (column === "name" ? "ascending" : "descending");
  sortColumn = column;
  sortProjects();
}));

function renderProjects() {
  let active = 0;
  let archived = 0;
  for (const row of projectRows) {
    if (row.dataset.archived === "true") archived += 1;
    else active += 1;
    row.hidden = (row.dataset.archived === "true") !== showingArchived;
    if (row.hidden) row.querySelector('input[type="radio"]').checked = false;
  }
  document.querySelector("#activeCount").textContent = active;
  document.querySelector("#archivedCount").textContent = archived;
  document.querySelector("#projectsEmpty").hidden = Boolean(showingArchived ? archived : active);
  activeTab.setAttribute("aria-selected", String(!showingArchived));
  archivedTab.setAttribute("aria-selected", String(showingArchived));
  archiveButton.textContent = showingArchived ? "Restore" : "Archive";
  archiveButton.disabled = !selectedRow();
  deleteButton.disabled = !selectedRow();
}

activeTab.addEventListener("click", () => { showingArchived = false; statusMessage.textContent = ""; renderProjects(); });
archivedTab.addEventListener("click", () => { showingArchived = true; statusMessage.textContent = ""; renderProjects(); });
projectRows.forEach((row) => row.querySelector('input[type="radio"]').addEventListener("change", renderProjects));

archiveButton.addEventListener("click", async () => {
  const row = selectedRow();
  if (!row) return;
  archiveButton.disabled = deleteButton.disabled = true;
  try {
    const form = new FormData();
    form.append("archived", String(!showingArchived));
    const response = await fetch(`/api/projects/${encodeURIComponent(row.dataset.projectId)}/archive`, { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not update project.");
    row.dataset.archived = String(!showingArchived);
    statusMessage.textContent = showingArchived ? "Project restored." : "Project archived.";
  } catch (error) { statusMessage.textContent = error.message || "Could not update project."; }
  renderProjects();
});

deleteButton.addEventListener("click", async () => {
  const row = selectedRow();
  if (!row) return;
  const name = row.querySelector(".project-name-link").textContent;
  if (!window.confirm(`Permanently delete "${name}" and all its jobs and files? This cannot be undone.`)) return;
  archiveButton.disabled = deleteButton.disabled = true;
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(row.dataset.projectId)}`, { method: "DELETE" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not delete project.");
    projectRows.splice(projectRows.indexOf(row), 1);
    row.remove();
    statusMessage.textContent = "Project deleted.";
  } catch (error) { statusMessage.textContent = error.message || "Could not delete project."; }
  renderProjects();
});

sortProjects();
renderProjects();
