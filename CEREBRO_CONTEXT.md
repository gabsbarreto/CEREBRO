# CEREBRO Context For Future LLM Agents

This file is a technical map of the current CEREBRO codebase. It is intended as reusable context for LLMs or developers making future changes.

Snapshot context:

- Repository: `gabsbarreto/CEREBRO`
- Current feature branch when this file was written: `pdf_table_parsing`
- App type: local FastAPI web app with Jinja templates and vanilla JavaScript
- Primary purpose: AI-assisted extraction from research PDFs and spreadsheet/text rows
- Runtime data location: `data/`
- Runtime data is intentionally ignored by Git

## 1. Product Overview

CEREBRO is an AI-assisted extraction console for scientific research workflows.

Users work inside projects. Each project has one immutable extraction type:

- `pdf`: PDF extraction from uploaded articles or folders of PDFs.
- `text`: Spreadsheet/text extraction from CSV/XLSX rows.
- `pdf_structured`: PDF extraction into schema-defined workbook-style tables.

Project type controls the dashboard:

- PDF projects open `/rq-screening?project_id=<project_id>`.
- Text projects open `/text?project_id=<project_id>`.
- Structured PDF projects open `/structured-pdf?project_id=<project_id>`.
- `/` redirects to the selected project's correct dashboard.

Core capabilities:

- Create and switch projects.
- Store jobs separately by project.
- Upload PDFs or folders of PDFs.
- Upload CSV/XLSX files and create one row job per spreadsheet row.
- Define structured PDF sheets with context, row unit, and ordered columns.
- Select saved prompt files or edit a system prompt in the UI.
- Select local or OpenAI model presets.
- Run PDF extraction through local OCR plus LLM extraction, or OpenAI PDF file/source mode.
- Run text extraction by constructing a row-level user prompt from mapped spreadsheet columns.
- Run structured PDF extraction by compiling sheet schemas into strict TSV prompts.
- Monitor queues and job statuses.
- Retry failed jobs/rows.
- Rerun PDF jobs with the same or different identity.
- Delete PDF jobs when not queued/running.
- Export project-scoped Excel reports.
- Preserve old legacy jobs through an idempotent migration into a default project.

## 2. Mental Model

CEREBRO is built around persisted filesystem jobs.

Each job is a directory containing:

- `metadata.json`: job identity, settings, source file, prompt, model, timing, and output paths.
- `status.json`: queue/running/completed/failed status, stage, progress, errors, and event history.
- `input/`: uploaded source file for PDF jobs.
- `outputs/`: generated prompts, model requests/responses, and final markdown output.
- Additional workflow folders such as rendered pages, OCR images, OCR text, or text row input.

The browser does not hold authoritative state. It polls backend endpoints, and the backend reconstructs job lists from `metadata.json` and `status.json`.

The project id must be threaded through every project-scoped API call. If a future change touches jobs, exports, duplicate checks, retry, rerun, queue polling, or output loading, verify that `project_id` is included.

## 3. Repository Layout

```text
.
|-- README.md
|-- CEREBRO_CONTEXT.md
|-- CEREBRO_UI_IDENTITY.md
|-- STRUCTURED_SHEET_IMPORT_GUIDE.md
|-- requirements.txt
|-- app/
|   |-- main.py
|   |-- config.py
|   |-- models.py
|   |-- services/
|   |   |-- projects.py
|   |   |-- jobs.py
|   |   |-- job_queue.py
|   |   |-- rq_screening_pipeline.py
|   |   |-- rq_completion.py
|   |   |-- text_extraction.py
|   |   |-- structured_extraction.py
|   |   |-- excel_summary.py
|   |   |-- rq_prompt.py
|   |   |-- renderer.py
|   |   |-- deepseek_ocr.py
|   |   |-- rq_llm.py
|   |   |-- openai_rq.py
|   |   |-- openai_inference_queue.py
|   |   |-- local_inference_worker.py
|   |   `-- process_control.py
|   |-- shared/
|   |   |-- cli.py
|   |   |-- rq_chat.py
|   |   |-- process_runner.py
|   |   |-- openai_responses.py
|   |   `-- mlx_runtime.py
|   |-- templates/
|   |   |-- rq_screening.html
|   |   |-- text_extraction.html
|   |   |-- structured_pdf.html
|   |   `-- project_new.html
|   `-- static/
|       |-- rq_screening.js
|       |-- text_extraction.js
|       |-- structured_pdf.js
|       `-- styles.css
|-- scripts/
|   |-- run_batch.py
|   |-- deepseek_ocr_worker.py
|   |-- rq_llm_worker.py
|   |-- rq_llm_persistent_worker.py
|   |-- openai_rq_worker.py
|   `-- find_deepseek_ocr.py
`-- tests/
    `-- test_shared_refactor.py
```

## 4. Runtime Data Layout

Runtime data lives under `data/` and is not committed.

```text
data/
|-- api_key.txt
|-- jobs/
|   `-- <legacy_job_id>/
|-- prompts/
|   `-- <prompt_file>.txt
|-- projects/
|   `-- <project_id>/
|       |-- project.json
|       |-- jobs/
|       |   `-- <job_id>/
|       |       |-- metadata.json
|       |       |-- status.json
|       |       |-- input/
|       |       |-- rendered_pages/
|       |       |-- ocr_images/
|       |       |-- ocr_text/
|       |       `-- outputs/
|       |-- source_files/
|       |   `-- <source_id>/
|       |       |-- source.json
|       |       |-- rows.jsonl
|       |       `-- <uploaded_spreadsheet>.csv|xlsx
|       |-- structured_sheets/
|       |   `-- <sheet_id>/
|       |       |-- sheet.json
|       |       |-- rows.jsonl
|       |       `-- errors.jsonl
|       |-- excluded_jobs/
|       |   `-- <job_id>/
|       |-- <project_slug>_rq_screening_summary.xlsx
|       |-- cerebro_<project_slug>_structured_pdf_export.xlsx
|       `-- cerebro_<project_slug>_text_extraction_export.xlsx
`-- queue_state.json
```

Important runtime rules:

- `data/jobs/` is legacy storage.
- `data/projects/<project_id>/jobs/` is the active project-scoped job store.
- `data/projects/<project_id>/excluded_jobs/` is used locally for archived duplicate jobs that should not appear in the UI/export.
- `data/projects/<project_id>/structured_sheets/` stores structured PDF sheet schemas, parsed rows, and parse errors.
- `data/prompts/` stores prompt files used by both PDF and text workflows.
- `data/api_key.txt` is an optional local OpenAI API key fallback.
- Do not force-add `data/` to Git. It can contain PDFs, extracted text, API logs, outputs, and sensitive review data.

## 5. Configuration

Main file: `app/config.py`.

Key directories:

- `BASE_DIR`
- `DATA_DIR`
- `JOBS_DIR`
- `PROJECTS_DIR`
- `PROMPTS_DIR`
- `TEMPLATES_DIR`
- `STATIC_DIR`

Important environment variables:

- `DEFAULT_OCR_DPI`
- `DEFAULT_OCR_BATCH_SIZE`
- `DEEPSEEK_OCR_MODEL`
- `DEEPSEEK_OCR_MAX_TOKENS`
- `DEEPSEEK_OCR_TEMPERATURE`
- `DEEPSEEK_OCR_PROMPT`
- `QWEN35_9B_8BIT_MODEL_PATH`
- `RQ_SCREENING_PROVIDER`
- `RQ_SCREENING_MODEL`
- `RQ_SCREENING_MAX_TOKENS`
- `RQ_SCREENING_THINKING_BUDGET`
- `OPENAI_RQ_SCREENING_MAX_TOKENS`
- `OPENAI_REASONING_EFFORT`
- `MAX_OPENAI_CONCURRENT_REQUESTS`
- `MAX_OCR_WORKERS`
- `OPENAI_INFERENCE_MAX_RETRIES`
- `OPENAI_INFERENCE_RETRY_BASE_SECONDS`
- `OPENAI_API_KEY`

The config module creates `data/`, `data/jobs/`, `data/projects/`, and `data/prompts/` on import.

`MAX_OPENAI_CONCURRENT_REQUESTS` defaults to `15`. It controls the OpenAI inference queue and the text extraction worker pool unless overridden by the environment.

## 6. Models And Presets

Main file: `app/models.py`.

Core classes:

- `JobStatus`: persisted status payload with status, stage, message, progress, error, and events.
- `JobSettings`: normalized settings parsed from forms and stored in metadata.

Model presets currently include:

- `qwen35_9b_8bit_reasoning`: public local MLX preset.
- `qwen36_27b_instruct`: hidden local preset.
- `openai_gpt5_mini_high`: public OpenAI GPT-5 mini preset with high reasoning.
- `openai_gpt54_mini_high`: public OpenAI GPT-5.4 mini preset with high reasoning.
- `openai_gpt54_mini_xhigh`: public OpenAI GPT-5.4 mini preset with xhigh reasoning.
- `openai_gpt54_nano_xhigh`: public OpenAI GPT-5.4 nano preset with xhigh reasoning and a 128,000-token model limit.
- GPT-5.6 Sol, Terra, and Luna are exposed with all supported reasoning efforts: `none`, `low`, `medium`, `high`, `xhigh`, and `max`. Preset IDs use `openai_gpt56_<tier>_<effort>`.

Provider normalization:

- Explicit provider values `local` and `openai` are respected.
- Models beginning with `gpt-`, `o1`, `o3`, or `o4` default to OpenAI if provider is unclear.
- OpenAI input mode can be `ocr_text` or `pdf_file`.
- `pdf_file` mode is only allowed for OpenAI. Local models always use `ocr_text`.

Prompt/model settings are copied into each job metadata at creation and completion. Retry of failed jobs should reuse the original stored settings rather than the current UI settings.

## 7. Project System

Main file: `app/services/projects.py`.

Project metadata is stored at:

```text
data/projects/<project_id>/project.json
```

Project metadata shape:

```json
{
  "project_id": "example-12345678",
  "name": "Project name",
  "description": "Brief description",
  "extraction_type": "pdf",
  "created_at": "...",
  "updated_at": "...",
  "is_default": false
}
```

Computed fields added when reading:

- `extraction_type_label`
- `dashboard_path`

Functions:

- `list_projects()`
- `create_project(name, description, extraction_type)`
- `get_project(project_id)`
- `get_default_project()`
- `migrate_legacy_jobs_if_needed()`
- `get_project_jobs_dir(project_id)`
- `validate_project_id(project_id)`
- `project_root(project_id)`
- `project_summary_path(project_id)`
- `project_dashboard_path(project)`
- `normalize_extraction_type(value)`

Default project:

- id: `legacy-jobs`
- name: `Legacy jobs`
- description: `Jobs created before project support was added.`
- extraction type: `pdf`

Legacy migration:

- Runs on app startup from `app.main.restore_queued_jobs`.
- Copies jobs from `data/jobs/` into `data/projects/legacy-jobs/jobs/`.
- Does not delete original legacy jobs.
- Stamps copied job metadata with `project_id` and `extraction_type: "pdf"`.
- Idempotent: existing destination job ids are skipped.

## 8. FastAPI Route Map

Main file: `app/main.py`.

Page routes:

```text
GET  /                  -> redirect to current/default project dashboard
GET  /rq-screening      -> PDF extraction dashboard
GET  /text              -> text extraction dashboard
GET  /structured-pdf    -> structured PDF extraction dashboard
GET  /projects/new      -> project creation form
POST /projects/new      -> create project and redirect to dashboard
```

Project API:

```text
GET  /api/projects
POST /api/projects
```

Prompt API:

```text
GET  /api/rq-prompt
POST /api/rq-prompt
GET  /api/rq-prompts
GET  /api/rq-prompts/{filename}
```

PDF job API:

```text
POST   /api/jobs
POST   /api/jobs/check-existing
GET    /api/jobs
GET    /api/jobs/{job_id}/status
GET    /api/jobs/{job_id}/result
GET    /api/jobs/{job_id}/download
POST   /api/jobs/{job_id}/rerun
DELETE /api/jobs/{job_id}
```

PDF queue/report API:

```text
GET  /api/queue
POST /api/queue/pause
POST /api/queue/resume
POST /api/queue/retry-failed
POST /api/queue/clean
GET  /api/reports/excel
```

Structured PDF extraction API:

```text
GET    /api/structured/sheets
POST   /api/structured/sheets
GET    /api/structured/sheets/{sheet_id}
GET    /api/structured/sheets/{sheet_id}/import-text
PUT    /api/structured/sheets/{sheet_id}
DELETE /api/structured/sheets/{sheet_id}
POST   /api/structured/sheets/parse-import
POST   /api/structured/sheets/{sheet_id}/duplicate
POST   /api/structured/workbook/duplicate
POST   /api/structured/columns/parse-blocks
POST   /api/structured/jobs
GET    /api/structured/jobs
GET    /api/structured/jobs/{job_id}/result
GET    /api/structured/rows
GET    /api/structured/export
```

Text extraction API:

```text
POST /api/text/jobs
GET  /api/text/jobs
GET  /api/text/jobs/counts
GET  /api/text/jobs/{job_id}/output
POST /api/text/jobs/{job_id}/retry
POST /api/text/jobs/retry-failed
GET  /api/text/export
```

Text queue API:

```text
POST /api/text/queue/pause
POST /api/text/queue/resume
```

Most job endpoints require `project_id`. For `GET` routes it is a query parameter; for `POST` routes it is normally form data.

## 9. PDF Extraction Workflow

Main files:

- `app/templates/rq_screening.html`
- `app/static/rq_screening.js`
- `app/main.py`
- `app/services/jobs.py`
- `app/services/job_queue.py`
- `app/services/rq_screening_pipeline.py`
- `app/services/rq_completion.py`
- `app/services/excel_summary.py`

User flow:

1. User selects a PDF project.
2. User uploads one or more PDFs, or a folder containing PDFs.
3. User selects model preset.
4. If OpenAI preset is selected, OpenAI API key field appears.
5. If OpenAI preset is selected, user can choose OpenAI PDF file/source extraction.
6. User edits/loads system prompt.
7. UI checks existing jobs with `/api/jobs/check-existing`.
8. UI submits to `/api/jobs`.
9. Backend creates one job directory per PDF under the current project's `jobs/`.
10. Backend queues each job with `JobQueue`.
11. Frontend polls queue and job status.
12. Completed jobs can be viewed inline, downloaded, rerun, deleted, or included in Excel export.

PDF job creation details:

- `POST /api/jobs` accepts `pdfs`, optional `pdf`, `pdf_relative_paths`, `project_id`, settings, prompt filename, prompt text, and `rerun_existing`.
- Job filename shown in UI comes from upload basename.
- Folder-relative path is stored in metadata as `source_relative_path`.
- Source folder is stored as `source_folder`.
- Uploaded file is saved as `input/uploaded.pdf`.
- SHA-256 is stored as `pdf_sha256`.
- Duplicate detection is scoped to current project and run identity:
  - filename
  - prompt filename
  - model
  - OpenAI input mode
- Reusable OCR is looked up by filename in current project.
- Reusable OpenAI file id is looked up by SHA-256 or basename in current project.

PDF pipeline stages:

1. `upload`: validate saved PDF.
2. `render`: render pages with `pypdfium2` into images.
3. `find_deepseek`: discover or use configured DeepSeekOCR2 model.
4. `ocr`: run OCR worker on rendered page images.
5. `merge`: merge OCR page markdown into `outputs/merged_full_text.txt`.
6. `prompt`: load or use system prompt and write:
   - `outputs/rq_prompt.txt`
   - `outputs/rq_system_prompt.txt`
   - `outputs/rq_user_prompt.txt`
7. `rq_model` or `openai_running`: run local or OpenAI extraction.
8. `complete`: write final output and append Excel report row.

OpenAI PDF file/source mode:

- Applies only when provider is OpenAI and `openai_input_mode == "pdf_file"`.
- Skips local OCR.
- Counts pages if possible.
- User prompt says to use the attached PDF and consider text, tables, figures, charts, captions, and appendices.
- OpenAI file id can be reused when the same PDF hash has already been uploaded.

Local OCR/text mode:

- Renders PDF pages.
- Runs DeepSeekOCR2.
- Merges OCR markdown.
- Sends merged text as the LLM user prompt.

Rerun behavior:

- `POST /api/jobs/{job_id}/rerun`.
- If the new settings match the original run identity, reruns the same job and clears old output files.
- If prompt/model/input mode differs, creates a child rerun job that reuses source OCR or OpenAI file data when available.
- Rerun child metadata includes fields such as `rerun_created_from_job_id`.

Delete behavior:

- `DELETE /api/jobs/{job_id}` removes the job directory.
- Active queued/running jobs cannot be deleted.

Excel report:

- `GET /api/reports/excel` rebuilds the project-scoped workbook from complete jobs.
- Workbook columns:
  - `job_id`
  - `filename`
  - `when it was inferenced`
  - `how long it took`
  - `LLM model`
  - `prompt`
  - `LLM output`

## 10. PDF Queue System

Main file: `app/services/job_queue.py`.

`JobQueue` is the PDF/OCR queue.

Characteristics:

- Uses worker threads.
- Worker count is `MAX_OCR_WORKERS`.
- Queue keys include project id: `<project_id>:<job_id>`.
- Queue status can be filtered by project.
- OpenAI inference is handed off to `OpenAIInferenceQueue` when `defer_openai=True`.
- Pause/resume is global because workers and subprocess cancellation are shared.
- Status responses include both OCR/local queue state and OpenAI queue state.

Important methods:

- `enqueue`
- `pause`
- `resume`
- `clean_queued`
- `retry_failed`
- `enqueue_screening_rerun`
- `enqueue_existing_queued_jobs`
- `mark_stale_running_jobs_failed`
- `status`

Pause behavior:

- `pause()` saves global paused state to `data/queue_state.json`.
- Running PDF work is cancelled through `process_control`.
- Cancelled jobs are returned to the front of the queue.

Resume behavior:

- `resume()` clears paused state.
- If UI settings are provided, pending jobs can have settings updated.
- Failed job retry uses original stored settings.

Startup recovery:

- Queued PDF jobs are restored on startup.
- Stale running PDF jobs are either requeued or marked failed depending on whether reusable source state exists.

## 11. OpenAI Inference Queue

Main file: `app/services/openai_inference_queue.py`.

This queue prevents network-bound OpenAI calls from blocking OCR workers.

Behavior:

- Bounded concurrency controlled by `MAX_OPENAI_CONCURRENT_REQUESTS`.
- Tracks pending and running OpenAI jobs.
- Retries retryable OpenAI errors using configured retry count/base delay.
- Calls `complete_screening_job` after successful inference.
- Exposes status so the PDF frontend can show active OpenAI workers separately from OCR workers.

OpenAI calls are executed by `app/services/openai_rq.py`, which delegates to `scripts/openai_rq_worker.py` through the shared event process runner.

OpenAI API key resolution order:

1. Form-provided key.
2. `OPENAI_API_KEY` environment variable.
3. `data/api_key.txt`.

## 12. Local OCR And LLM Processing

PDF rendering:

- `app/services/renderer.py`
- Uses `pypdfium2`.
- Renders pages to images for OCR.

DeepSeek OCR:

- `app/services/deepseek_ocr.py`
- Uses `scripts/deepseek_ocr_worker.py`.
- Can auto-discover local model via `discover_deepseek_model()`.
- `scripts/find_deepseek_ocr.py` helps locate local DeepSeekOCR2 model folders.

Local LLM:

- `app/services/rq_llm.py`
- Uses `scripts/rq_llm_worker.py` or persistent worker support.
- Shared prompt assembly is in `app/shared/rq_chat.py`.
- MLX cleanup helpers are in `app/shared/mlx_runtime.py`.

Subprocess/event handling:

- `app/shared/process_runner.py` runs worker scripts and parses JSON event lines.
- `app/shared/cli.py` contains JSON event emission and boolean parsing helpers.
- `app/services/process_control.py` tracks subprocesses and cancellation requests.

## 13. Prompt System

Main file: `app/services/rq_prompt.py`.

Prompts live in:

```text
data/prompts/
```

Prompt behavior:

- Both PDF and text workflows use prompt files as system prompts.
- UI can load and save prompts.
- If the UI provides a system prompt directly, that text is used and `rq_prompt_source_path` is empty.
- Otherwise the prompt file is read from `data/prompts/`.
- Prompt filename is stored in job metadata as `rq_prompt_filename`.
- System and user prompts used for each job are persisted for reproducibility.

Endpoints:

- `GET /api/rq-prompt`
- `POST /api/rq-prompt`
- `GET /api/rq-prompts`
- `GET /api/rq-prompts/{filename}`

Prompt file safety:

- Prompt filenames are sanitized by `sanitize_prompt_filename`.
- Default prompt file is configured by `DEFAULT_RQ_PROMPT_FILENAME`.

## 14. Structured PDF Extraction Workflow

Main files:

- `app/templates/structured_pdf.html`
- `app/static/structured_pdf.js`
- `app/services/structured_extraction.py`
- `app/services/rq_completion.py`

User flow:

1. User creates/selects a `pdf_structured` project.
2. The dashboard opens with PDF intake first, then a workbook schema/spreadsheet panel, then diagnostics.
3. The workbook panel has sheet tabs and a `+` sheet button, similar to Excel.
4. The sheet name, context, and `More information / other preferences` fields sit above the spreadsheet grid.
5. The user names active columns directly in the spreadsheet header.
6. Each named column is mirrored into a column instruction card below the grid.
7. The spreadsheet grid also renders inactive light-gray columns to the right of active schema columns, so the table looks complete even before instructions exist.
8. Hovering the separator after the last active column reveals a blue vertical line and a small plus circle; clicking it adds a new active column and focuses the new header.
9. Only active columns are persisted in the sheet schema. Inactive gray columns are a UI affordance and do not create backend schema columns until the user adds one.
10. Each active column stores a column name, question, and rules/examples text.
11. The sheet-level form stores a sheet name, context, and `More information / other preferences` text. This is persisted as `row_unit` for backward compatibility.
12. Users can paste either columns-only text or a full sheet definition with `Paste sheet / columns`.
13. The unified import parser can fill sheet name, context, more information/preferences, and columns from one text block.
14. If imported content conflicts with existing sheet fields or column names, the UI shows one overwrite/cancel confirmation listing every conflict.
15. Draft sheets autosave after edits; extraction cannot run until the schema is complete.
16. A sheet locks as soon as its first structured extraction job is queued. Locked sheets are read-only.
17. Locked sheets can be duplicated to edit the copied schema. Duplication copies sheet name, context, preferences, and columns, but not rows, parse errors, jobs, or lock metadata.
18. `Duplicate workbook` opens a sheet checklist and creates a new `pdf_structured` project containing only the selected sheet schemas in source order.
19. Workbook copies preserve the project description and use the next available `Project name (n)` name. They do not copy PDFs, jobs, rows, errors, outputs, or sheet locks.
20. The backend compiles the sheet schema into strict TSV extraction instructions.
21. User uploads one or more PDFs or a folder of PDFs.
22. Backend creates one PDF job per uploaded file and stores the compiled structured prompt in the job metadata/output prompts.
23. The existing PDF OCR/OpenAI pipeline runs as usual.
24. Completion is intercepted for `extraction_type: "pdf_structured"` and parses the model response as TSV.
25. Parsed rows are appended to the selected sheet's `rows.jsonl`; parse failures are appended to `errors.jsonl`.
26. The UI shows rows in a fixed-height virtual table and exposes raw output/parse errors per job.
27. Export creates one Excel worksheet per structured sheet.

Current structured PDF panel order:

1. `PDF intake`: file/folder upload, model preset, OpenAI key/file mode, OCR settings, run button.
2. `Workbook schema`: sheet tabs, sheet name, context, more information/preferences, spreadsheet grid, column instruction cards, generated prompt preview.
3. `Diagnostics`: structured jobs, parse status, raw output, parsed rows, parse errors.

Structured sheet import:

- User-facing guide: `STRUCTURED_SHEET_IMPORT_GUIDE.md`.
- UI actions: `Paste sheet / columns` imports sheet text; `Export sheet text` generates a paste-ready full sheet block for reuse.
- Backend parser: `structured_extraction.parse_sheet_import()`.
- Backend exporter: `structured_extraction.format_sheet_import_text()`.
- API route: `POST /api/structured/sheets/parse-import`.
- API route: `GET /api/structured/sheets/{sheet_id}/import-text`.
- Accepted modes:
  - Full sheet import with `Sheet name ###`, `Context ###`, `More information / other preferences ###`, `Columns ###`, and column blocks.
  - Columns-only import using `Column name ###`, `Question ###`, `Rules ###`, separated by `---`.
- Import conflict detection compares pasted content against the current browser sheet state sent by the frontend.
- Conflicts include existing context, more information/preferences, and duplicate column names. Sheet name imports do not trigger an overwrite prompt.
- The API only parses and reports conflicts. The frontend applies imported data after confirmation and autosave persists the draft.

Structured sheet locking:

- Backend helper: `structured_extraction.lock_sheet_for_first_run(project_id, sheet_id, job_id)`.
- Duplicate helper: `structured_extraction.duplicate_sheet(project_id, sheet_id)`.
- Duplicate route: `POST /api/structured/sheets/{sheet_id}/duplicate`.
- Workbook duplicate helper: `structured_extraction.duplicate_workbook(project_id, sheet_ids)`.
- Workbook duplicate route: `POST /api/structured/workbook/duplicate`.
- Lock metadata in `sheet.json`:

```json
{
  "locked_at": "...",
  "locked_by_job_id": "...",
  "locked_reason": "First extraction run was queued."
}
```

- `PUT /api/structured/sheets/{sheet_id}` rejects edits to locked sheets.
- The structured PDF frontend disables schema fields, column controls, import, and autosave on locked sheets.
- Running a locked sheet is allowed; editing it is not.

Structured sheet storage:

```text
data/projects/<project_id>/structured_sheets/<sheet_id>/
|-- sheet.json
|-- rows.jsonl
`-- errors.jsonl
```

Structured job files include:

```text
data/projects/<project_id>/jobs/<job_id>/outputs/
|-- rq_system_prompt.txt
|-- rq_user_prompt.txt
|-- rq_screening_output.md
|-- structured_raw_response.tsv
|-- structured_parsed_rows.json
`-- structured_parse_errors.json
```

Prompt compilation:

- The sheet schema is the source of truth.
- The user does not manually write the final TSV header.
- The compiled prompt includes context, other preferences, each column question/rules, and a required TSV header in the configured column order.
- The prompt forbids Markdown tables, code fences, bullets, introductory text, and extra lines.
- Prompt compilation requires named columns and completed questions. Draft sheets expose `schema_ready: false` and `schema_error`.

TSV parsing:

- The first non-empty line must exactly match the generated header.
- Markdown tables and code fences are rejected where possible.
- Header-only output is valid and produces zero parsed rows.
- Each data row must have exactly the expected number of cells.
- Empty cells are allowed, including trailing empty cells.
- Raw model output is preserved even when parsing fails.

Structured export:

- `GET /api/structured/export`
- Workbook file name pattern:

```text
cerebro_<project_slug>_structured_pdf_export.xlsx
```

- Each worksheet includes:
  - `source_pdf`
  - `job_id`
  - `extracted_at`
  - `model`
  - `parse_status`
  - `parse_date`
  - `parse_error`
  - sheet-defined columns in order

## 15. Text Extraction Workflow

Main files:

- `app/templates/text_extraction.html`
- `app/static/text_extraction.js`
- `app/services/text_extraction.py`

User flow:

1. User creates/selects a text extraction project.
2. User uploads a `.csv` or `.xlsx` file.
3. User maps one or more spreadsheet columns to prompt labels.
4. User optionally enters a Study ID column.
5. CEREBRO freezes that source and mapping at project level and creates `Sheet 1`.
6. User selects a model preset and prompt for the active workbook sheet.
7. Running the sheet creates one independently queued job per nonblank spreadsheet row.
8. The sheet locks on first run. Duplicate creates an editable prompt/model variant with no copied jobs or outputs.
9. UI shows the mapped source columns and sheet-specific results in a fixed-height virtualized spreadsheet.
10. Workbook export creates one worksheet per text extraction sheet and restores all original source columns.

Supported files:

- `.csv`
- `.xlsx`
- `.xls` is explicitly rejected with a message to save as `.xlsx` or CSV.

Source storage:

```text
data/projects/<project_id>/source_files/<source_id>/
|-- source.json
|-- rows.jsonl
`-- <safe_uploaded_filename>.csv|xlsx

data/projects/<project_id>/
|-- text_workbook.json
`-- text_sheets/
    `-- <sheet_id>/
        `-- sheet.json
```

`text_workbook.json` identifies the active project source and records that its mapping is frozen. Each text `sheet.json` stores sheet name/order, source id, prompt filename/content, model preset/model, timestamps, and first-run lock metadata.

Text row job files:

```text
data/projects/<project_id>/jobs/<job_id>/
|-- metadata.json
|-- status.json
|-- row_input.json
|-- system_prompt.txt
|-- user_prompt.txt
|-- output.md
`-- outputs/
    |-- rq_prompt.txt
    |-- rq_system_prompt.txt
    |-- rq_user_prompt.txt
    `-- rq_screening_output.md
```

Text job metadata includes:

- `extraction_type: "text"`
- `project_id`
- `text_sheet_id`
- `text_sheet_name`
- `source_id`
- `source_filename`
- `stored_source_file`
- `record_id`
- `study_id_column`
- `source_row_index`
- `row_display_number`
- `spreadsheet_row_number`
- `project_row_order`
- `input_preview`
- `selected_input_fields`
- prompt/model/settings fields
- timing and error fields after execution

Column mapping:

- Each mapping has `column_name` and `prompt_label`.
- Column names are trimmed and must exactly match spreadsheet headers after normalization.
- The mapping is immutable after the project source is created and is shared by every sheet.
- Empty cell values are preserved.
- User prompt format:

```text
Prompt label 1: <cell value>

Prompt label 2: <cell value>
```

Study ID behavior:

- Optional Study ID column is validated against spreadsheet headers.
- If present and nonempty for a row, its cell value becomes `record_id`.
- Otherwise `record_id` falls back to `Row <row_display_number>`.

Text queue:

- `TextJobQueue` is separate from `JobQueue`.
- Worker count is `MAX_OPENAI_CONCURRENT_REQUESTS` with a minimum of 1 (default `15`).
- Local text inference remains capped at 4 concurrent calls; the larger worker pool is intended for OpenAI throughput.
- Pause stops future row starts; active model calls are allowed to finish.
- Retry only applies to failed rows.
- Retry requeues the same row job and preserves row order.
- Retry uses original stored job settings.

Text list API:

```text
GET /api/text/jobs?project_id=<id>&sheet_id=<sheet_id>&offset=0&limit=100&status=failed&search=abc
```

Response shape:

```json
{
  "project": {},
  "items": [],
  "total": 0,
  "offset": 0,
  "limit": 100
}
```

Workbook APIs:

```text
GET  /api/text/workbook
POST /api/text/source
POST /api/text/sheets
PUT  /api/text/sheets/{sheet_id}
POST /api/text/sheets/{sheet_id}/duplicate
POST /api/text/sheets/{sheet_id}/run
```

Server-side filtering:

- Status: `all`, `not_run`, `queued`, `running`, `completed`, `failed`.
- Search includes record id, mapped cell values, input preview, row number, and job id.
- Limit is capped at 500.

Text export:

- `GET /api/text/export`
- Creates one worksheet per text extraction sheet in sheet order.
- Preserves every original source column in every worksheet, including columns hidden from the browser grid.
- Appends:
  - `cerebro_extracted_at`
  - `cerebro_processing_time_seconds`
  - `cerebro_model_used`
  - `cerebro_prompt_used`
  - `cerebro_status`
  - `cerebro_error`
  - `cerebro_output`
- Preserves source row order.
- Includes not-run/queued/running/failed rows with status and blank output where appropriate.
- File name pattern:

```text
cerebro_<project_slug>_text_extraction_export.xlsx
```

## 16. Frontend Structure

The frontend is Jinja-rendered HTML plus vanilla JavaScript and one shared stylesheet.

Templates:

- `rq_screening.html`: PDF extraction dashboard.
- `text_extraction.html`: spreadsheet/text extraction dashboard.
- `structured_pdf.html`: structured PDF sheet/table dashboard.
- `project_new.html`: project creation page.

Static JS:

- `rq_screening.js`: PDF upload, prompt controls, queue polling, duplicate checks, rerun/delete, result panels, Excel report link, project sidebar.
- `text_extraction.js`: frozen source mapping, text workbook tabs, sheet prompt/model autosave, virtualized spreadsheet rows, retry/export, project sidebar.
- `structured_pdf.js`: workbook sheet tabs, editable grid headers, synchronized column cards, PDF upload, virtualized row table, parse diagnostics, export, project sidebar.

Styles:

- `styles.css`: app-wide visual identity, project sidebar, PDF UI, text UI, virtual table, status badges.

Shared frontend project behavior:

- Project id is injected as `body[data-current-project-id]` and hidden `#currentProjectId`.
- Project list is injected as JSON in `#projectData`.
- Model presets are injected as JSON in `#modelPresetData`.
- Sidebar fetches `/api/projects` and renders project names plus extraction type subtitles.
- Clicking a project uses its `dashboard_path`.
- Project-scoped links use `withProject(url)`.

PDF frontend polling:

- Job status polling every 1.5 seconds for active jobs.
- Full job-list refresh every 10 seconds.
- `/api/jobs?limit=0&project_id=<id>` is used to restore all project jobs.
- Inline result panels fetch `/api/jobs/{job_id}/result`.
- Queue state fetches `/api/queue`.

Text frontend polling:

- Counts poll every 2.5 seconds.
- Visible window refresh every 3 seconds.
- Spreadsheet rows are not all rendered. The UI uses a fixed row height and a scroll spacer.
- Visible windows request `/api/text/jobs` with `sheet_id`, `offset`, `limit`, `status`, and `search`.
- Constants:
  - `ROW_HEIGHT = 42`
  - `WINDOW_LIMIT = 120`
  - `SCROLL_OVERSCAN = 12`

Text table columns:

- Row
- Status
- Study ID / Record ID
- One visible cell column for each project-level mapped input column
- CEREBRO output
- Actions

The source may contain additional columns, but those are intentionally omitted from the browser grid and restored in every exported worksheet.

Structured PDF table columns:

- Source PDF
- Parse status
- Parse date
- Sheet-defined columns in configured order
- Header cells for sheet-defined columns are editable and sync back to the sheet schema.
- Inactive light-gray columns are appended after the last active schema column.
- The active/inactive boundary has a hover add-column affordance: blue line plus circle.
- Header inputs and column instruction fields are disabled once a sheet is locked.
- The rows API merges persisted parsed/error rows with live job placeholder rows, so queued/running PDFs appear before parsing completes.
- Structured PDF polling force-refreshes the visible row window so status changes update automatically.

Status class conventions:

- `complete` / `completed`
- `running`
- `queued`
- `failed`

## 17. UI Identity

Design guidance is in `CEREBRO_UI_IDENTITY.md`.

High-level visual identity:

- Scientific, focused, neural scanning workstation feel.
- Dark navy/graphite surfaces.
- Cyan/teal/violet/blue accents.
- Strong contrast and visible focus states.
- Do not introduce unrelated redesigns when making functional changes.

When editing UI:

- Preserve existing IDs and form field names unless intentionally updating JS and backend together.
- Do not invent mock statuses or fake progress.
- Use real backend queue/job data.
- Keep text fitting and avoid horizontal overflow.

## 18. Scripts

Batch processing:

- `scripts/run_batch.py`
- Runs PDF screening over a folder or list of PDF paths.
- Supports `--project-id`.
- Processes sequentially.
- Uses the same `JobSettings`, `jobs.create_job`, and `run_job` pipeline as the app.

Worker scripts:

- `scripts/deepseek_ocr_worker.py`: OCR worker.
- `scripts/rq_llm_worker.py`: one-shot local LLM worker.
- `scripts/rq_llm_persistent_worker.py`: persistent local LLM worker support.
- `scripts/openai_rq_worker.py`: OpenAI Responses API worker.

Utility:

- `scripts/find_deepseek_ocr.py`: searches likely local locations for DeepSeekOCR2 model folders.
- `scripts/_bootstrap.py`: ensures scripts can import the project root.

## 19. Testing

Primary test file:

```text
tests/test_shared_refactor.py
```

Current targeted test command:

```bash
PYTHONPATH=. pytest -q tests/test_shared_refactor.py
```

Covered areas include:

- Shared boolean parsing.
- Chat prompt construction and thinking tag stripping.
- OpenAI response parsing.
- Event subprocess runner.
- OpenAI API key resolution order.
- GPT-5.4 mini high/xhigh and GPT-5.4 nano xhigh presets, plus all GPT-5.6 Sol/Terra/Luna reasoning combinations.
- OpenAI PDF file mode.
- Job identity matching.
- OCR and OpenAI file reuse helpers.
- Rerun child jobs.
- Pipeline OpenAI PDF file mode.
- Deferred OpenAI queue behavior.
- OpenAI transient retry behavior.
- Key route smoke tests.
- Excel summary migration/rebuild behavior.
- Structured PDF project type, sheets, column block parser, prompt compiler, TSV parser, row scoping, and export smoke test.

When adding features, prefer extending these tests rather than relying only on manual UI checks.

## 20. Common Change Points

Add or change model presets:

- Edit `app/models.py`.
- Ensure `public_model_presets()` exposes only intended presets.
- Update tests for preset id, label, provider, model, reasoning effort.
- Verify PDF, text, and structured PDF templates render the preset list.

Add project behavior:

- Edit `app/services/projects.py`.
- Verify route redirects in `app/main.py`.
- Update `rq_screening.js`, `text_extraction.js`, and `structured_pdf.js` if sidebar or project switch behavior changes.
- Preserve `extraction_type` backward compatibility.

Change PDF job behavior:

- Edit `app/main.py`, `app/services/jobs.py`, `app/services/job_queue.py`, and/or `app/services/rq_screening_pipeline.py`.
- Ensure duplicate checks and reruns are project-scoped.
- Ensure output files and metadata paths remain compatible with `/api/jobs/{job_id}/result`.
- Rebuild Excel report behavior if metadata filename semantics change.

Change text job behavior:

- Edit `app/services/text_extraction.py`, `app/static/text_extraction.js`, and `app/templates/text_extraction.html`.
- Keep listing windowed. Do not render all rows.
- Keep row order stable through `project_row_order`.
- Retry failed rows by resetting the existing job, not creating duplicate row jobs.

Change structured PDF behavior:

- Edit `app/services/structured_extraction.py`, `app/static/structured_pdf.js`, and `app/templates/structured_pdf.html`.
- Keep the generated TSV header derived from sheet columns.
- Keep structured rows windowed/virtualized. Do not render all rows.
- Keep inactive spreadsheet columns as visual affordances unless intentionally adding schema fields.
- Keep locked sheets immutable. Add new edit workflows through duplication, not direct mutation.
- Preserve raw output and parse errors for each job.

Change prompts:

- Edit `app/services/rq_prompt.py`.
- Validate prompt filename handling.
- Ensure both PDF and text UIs still load/save prompt files.
- Preserve stored prompt files per job for reproducibility.

Change exports:

- PDF export: `app/services/excel_summary.py`.
- Text export: `app/services/text_extraction.py`.
- Structured PDF export: `app/services/structured_extraction.py`.
- Keep exports project-scoped.
- Avoid reading ignored `excluded_jobs` unless intentionally building an audit report.

## 21. API Payload Notes

PDF upload form fields:

- `pdfs`
- `pdf`
- `pdf_relative_paths`
- `project_id`
- `ocr_dpi`
- `ocr_batch_size`
- `deepseek_ocr_model_path`
- `rq_model_preset`
- `openai_api_key`
- `openai_input_mode`
- `rq_prompt_filename`
- `rq_system_prompt`
- `rerun_existing`

Text upload form fields:

- `spreadsheet`
- `project_id`
- `column_mappings` as JSON list
- `study_id_column`
- `rq_model_preset`
- `openai_api_key`
- `rq_prompt_filename`
- `rq_system_prompt`

`column_mappings` example:

```json
[
  {"column_name": "title", "prompt_label": "Title"},
  {"column_name": "abstract", "prompt_label": "Abstract"}
]
```

Structured PDF upload form fields:

- `pdfs`
- `pdf`
- `pdf_relative_paths`
- `project_id`
- `sheet_id`
- `ocr_dpi`
- `ocr_batch_size`
- `deepseek_ocr_model_path`
- `rq_model_preset`
- `openai_api_key`
- `openai_input_mode`

Structured sheet form fields:

- `project_id`
- `name`
- `context`
- `row_unit`
- `columns` as JSON list

`columns` example:

```json
[
  {"column_name": "SpeciesLatinArticle", "question": "State the scientific name.", "rules": "Enter NA if absent."}
]
```

Structured import parser form fields:

- `project_id`
- `sheet_id`
- `block_text`
- `current_name`
- `current_context`
- `current_row_unit`
- `current_columns` as JSON list

Structured import parser response:

```json
{
  "fields": {
    "name": "Species characteristics",
    "context": "Review context.",
    "row_unit": "One row per species."
  },
  "columns": [
    {"column_name": "SpeciesLatinArticle", "question": "State the scientific name.", "rules": "Enter NA if absent."}
  ],
  "count": 1,
  "has_conflicts": true,
  "conflicts": {
    "fields": ["Context"],
    "columns": ["SpeciesLatinArticle"]
  }
}
```

PDF job status shape:

```json
{
  "job_id": "...",
  "status": "queued|running|complete|failed",
  "stage": "queued|render|ocr|merge|prompt|rq_model|rq_screening|openai_queued|openai_running|complete|error",
  "message": "...",
  "progress": 0.0,
  "error": null,
  "events": []
}
```

Text serialized row shape:

```json
{
  "job_id": "...",
  "project_id": "...",
  "row": 1,
  "row_order": 0,
  "status": "not_run|queued|running|completed|failed",
  "status_label": "Queued",
  "stage": "...",
  "message": "...",
  "error": "",
  "record_id": "Row 1",
  "input_preview": "...",
  "mapped_cells": {"title": "Example title", "abstract": "Example abstract"},
  "model": "...",
  "prompt": "...",
  "started_at": "",
  "completed_at": "",
  "duration_seconds": null,
  "result_preview": ""
}
```

## 22. Current Implementation Notes And Sharp Edges

These are useful checks for future LLMs before editing:

- `data/` is ignored. Changes to project metadata, excluded jobs, and generated reports are local runtime state, not source code changes.
- `project_id` scoping is central. Missing it can leak jobs across projects.
- PDF pause/resume is global even though status is project-filtered.
- Text pause/resume is a separate queue and lets active rows finish.
- Text extraction listing is server-windowed and frontend-virtualized. Avoid replacing it with all-row DOM rendering.
- Text projects have one frozen source/mapping in `text_workbook.json`; sheets vary prompt/model configuration, not source columns.
- Legacy text jobs are adopted idempotently into locked text sheets and receive `text_sheet_id` metadata without recreating jobs.
- Text sheets lock on first run. Duplicates are inserted directly after the source sheet and copy configuration without jobs/results.
- Existing projects without `extraction_type` are treated as PDF projects by `normalize_extraction_type`.
- Structured PDF projects use `extraction_type: "pdf_structured"` and route to `/structured-pdf`.
- `openai_gpt54_mini_high` and `openai_gpt54_mini_xhigh` are public presets for `gpt-5.4-mini` with `high` and `xhigh` reasoning, respectively.
- `openai_gpt54_nano_xhigh` is a public preset for `gpt-5.4-nano` with `xhigh` reasoning and caps output at the model's 128,000-token limit.
- GPT-5.6 presets cover `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna` at `none`, `low`, `medium`, `high`, `xhigh`, and `max`; all cap output at 128,000 tokens.
- Prompt files are shared globally across projects, not stored per project.
- Runtime Excel summaries can be rebuilt from active jobs.
- Structured PDF parse failures still mark the underlying model job complete; the parse status is carried separately in metadata and sheet error records.
- Structured sheet row/error ledger updates are serialized per sheet so concurrently completing jobs cannot overwrite each other's records.
- Structured PDF inactive spreadsheet columns are visual only. A new schema column is created only when the user uses the `+ Column` button, pastes column blocks, or clicks the plus divider after the last active column.
- Structured PDF sheet imports are parser-only on the backend. The frontend owns conflict confirmation and merge behavior before autosave.
- Structured PDF sheets lock on first queued run. Duplicates are unlocked and intentionally do not copy rows/errors.
- Jobs under `excluded_jobs/` are not seen by normal `jobs.list_jobs()` because that function reads only the active `jobs/` folder.
- If touching `app/main.py` or `app/services/text_extraction.py`, scan nearby code for accidental duplicated lines before building on them.

## 23. Suggested Manual Smoke Tests

Project flow:

1. Start the app.
2. Create a PDF project.
3. Create a text project.
4. Switch projects from the sidebar.
5. Confirm each project opens the correct dashboard.

PDF flow:

1. Open a PDF project.
2. Upload a small PDF.
3. Select a prompt and model.
4. Queue the job.
5. Confirm status updates and final output.
6. Open inline result.
7. Download Excel report.
8. Try rerun and delete on a completed job.

Text flow:

1. Open a text project.
2. Upload a small CSV/XLSX with `title`, `abstract`, and `doi`.
3. Map `title -> Title` and `abstract -> Abstract`.
4. Set Study ID column to `doi` or leave blank.
5. Confirm `Sheet 1` opens and only the mapped input columns appear in the white spreadsheet grid.
6. Select a prompt/model and run the sheet.
7. Confirm counts and visible row statuses update.
8. Duplicate the sheet and confirm the duplicate is directly to its right, editable, and contains no jobs/results.
9. Filter by status and search by Study ID / Record ID.
10. Open a row output and retry a failed row if available.
11. Export the workbook and confirm every worksheet contains all original source columns.

Large text performance check:

1. Upload a CSV with tens of thousands of rows.
2. Confirm the browser renders only the visible row window.
3. Confirm `/api/text/jobs` uses `sheet_id`, `offset`, and `limit`.
4. Confirm polling does not download all rows repeatedly.

Structured PDF flow:

1. Create a structured PDF project.
2. Open `/structured-pdf?project_id=<id>`.
3. Confirm a workbook-style sheet tab and editable spreadsheet header are visible.
4. Use the `+` sheet button to add another worksheet if needed.
5. Rename sheet columns directly in the spreadsheet header.
6. Confirm inactive light-gray columns appear to the right of active schema columns.
7. Hover the separator after the last active column and confirm a blue line and plus circle appear.
8. Click the plus divider and confirm a new active column appears and receives focus.
9. Confirm each active column has a matching question/rules card below the grid.
10. Fill column questions and any rules/examples.
11. Use `More information / other preferences` for sheet-level guidance.
12. Paste many columns using `Column name ###`, `Question ###`, `Rules ###`, separated by `---` if bulk entry is easier.
13. Paste a full sheet definition using `Sheet name ###`, `Context ###`, `More information / other preferences ###`, `Columns ###`, and column blocks.
14. Confirm duplicate pasted fields/columns trigger one overwrite/cancel prompt.
15. Wait for autosave and confirm the generated prompt preview contains the TSV header.
16. Upload a small PDF and run extraction.
17. Confirm the sheet locks after the run is queued.
18. Duplicate the locked sheet and confirm the duplicate is editable and has no parsed rows/errors.
19. Confirm parsed rows appear, or a clear parse error is shown with raw output preserved.
20. Export the workbook and confirm one worksheet per structured sheet.

## 24. Development Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run app:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run tests:

```bash
PYTHONPATH=. pytest -q tests/test_shared_refactor.py
```

Check Git state:

```bash
git status --short --branch
```

## 25. Principle For Future Changes

Make changes by following the existing data contracts rather than inventing new ones.

In practice:

- Read `metadata.json` and `status.json` shapes before changing a workflow.
- Keep project-scoped behavior project-scoped.
- Keep prompt/model settings reproducible per job.
- Preserve existing PDF behavior when adding table parsing or other PDF enhancements.
- Keep text extraction performant for large spreadsheets.
- Treat `data/` as user/runtime data, not application source.
