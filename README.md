# CEREBRO

CEREBRO is an AI-assisted scientific data extraction tool for PDFs, spreadsheet/text records, and workbook-style structured PDF extraction.

Users create or select a project, choose an extraction type, choose a model, and send files or spreadsheet rows to a processing queue. PDF projects can process a primary article with optional supporting PDF, XLSX, or CSV files through either local OCR plus model extraction, or through OpenAI file/source extraction. Text projects process CSV/XLSX rows by assembling selected cell values into row-level user prompts. Structured PDF projects let users define workbook sheets and column-level extraction instructions, then parse model output into Excel-style tables.

## 1. What The App Does

CEREBRO helps screen and extract structured information from scientific papers.

Core workflow:

1. Create or select a project.
2. Choose a project type: PDF extraction, text extraction, or structured PDF extraction.
3. For PDF extraction, upload primary PDFs individually or as a folder, then optionally attach supporting PDFs, XLSX, or CSV files to the matching study.
4. Choose a processing pathway:
   - OCR/text pathway: render PDF pages, run local OCR, merge text, then send the text to a local model or OpenAI model.
   - OpenAI file/source pathway: upload the PDF to OpenAI and send the file source with the extraction prompt.
5. For text extraction, upload one CSV/XLSX source, map the prompt input columns, and work with prompt/model variants as workbook sheets.
6. For structured PDF extraction, create workbook sheets, name columns in the spreadsheet grid, fill matching question/rules boxes, and run PDFs against the selected sheet.
7. Choose a model preset.
8. Provide an OpenAI API key when using OpenAI models.
9. Write or load an extraction prompt for standard PDF/text projects, or let CEREBRO compile a strict TSV prompt from the structured sheet schema.
10. Add files or rows to the current project's queue.
11. Monitor project-specific progress, retry failed jobs/rows where supported, view outputs, and download a project-specific Excel report/export.

The app stores runtime job data locally under `data/`. This includes uploaded PDFs, OCR text, OpenAI request/response logs, job metadata, queue state, and generated Excel reports. The `data/` folder is intentionally ignored by Git.

Project types and dashboards:

- `pdf`: standard PDF extraction at `/rq-screening?project_id=<project_id>`.
- `text`: spreadsheet/text row extraction at `/text?project_id=<project_id>`.
- `pdf_structured`: structured PDF workbook extraction at `/structured-pdf?project_id=<project_id>`.
- Existing projects without an `extraction_type` are treated as `pdf` projects for backward compatibility.

## 2. Structure

```text
CEREBRO/
|-- app/
|   |-- main.py                       # FastAPI routes and app entrypoint
|   |-- config.py                     # Runtime configuration and environment defaults
|   |-- models.py                     # Job settings, model presets, and status models
|   |-- services/
|   |   |-- projects.py               # Project metadata, routing, and legacy migration
|   |   |-- rq_screening_pipeline.py  # Main PDF processing pipeline
|   |   |-- job_queue.py              # Queue, pause/resume, retry, cleanup
|   |   |-- text_extraction.py        # Spreadsheet parsing, row jobs, text queue, export
|   |   |-- structured_extraction.py  # Structured workbooks/sheets, TSV parsing, row storage, export
|   |   |-- structured_sources.py     # Reusable structured-project PDF study library
|   |   |-- supplementary_sources.py  # Supporting CSV/XLSX transcript generation
|   |   |-- jobs.py                   # Job folders, metadata, and status files
|   |   |-- renderer.py               # PDF page rendering
|   |   |-- deepseek_ocr.py           # DeepSeek OCR integration
|   |   |-- openai_rq.py              # OpenAI Responses API calls
|   |   |-- openai_inference_queue.py # Parallel OpenAI inference queue
|   |   |-- rq_prompt.py              # Prompt loading/saving/building
|   |   `-- excel_summary.py          # Excel report generation
|   |-- static/
|   |   |-- styles.css                # CEREBRO UI styling
|   |   |-- rq_screening.js           # PDF extraction browser UI behaviour
|   |   |-- text_extraction.js        # Text extraction browser UI behaviour
|   |   |-- structured_pdf.js         # Structured PDF workbook UI behaviour
|   |   `-- study_bundles.js          # Shared primary/supporting-file picker
|   `-- templates/
|       |-- rq_screening.html         # PDF extraction dashboard page
|       |-- text_extraction.html      # Text extraction dashboard page
|       |-- structured_pdf.html       # Structured PDF dashboard page
|       `-- project_new.html          # Project creation form
|-- scripts/                          # Worker and batch helper scripts
|-- tests/                            # Backend/unit smoke tests
|-- CEREBRO_UI_IDENTITY.md            # UI identity and contribution notes
|-- STRUCTURED_SHEET_IMPORT_GUIDE.md  # User guide and LLM prompt for sheet imports
|-- requirements.txt                  # Python dependencies
|-- LICENSE                           # GPL-3.0 license
`-- README.md
```

Runtime-only folders/files:

```text
data/
|-- api_key.txt                       # Optional local OpenAI key file
|-- jobs/                             # Legacy pre-project jobs, retained for safe migration
|-- projects/
|   `-- <project_id>/
|       |-- project.json              # Project metadata, including extraction_type
|       |-- source_files/             # Uploaded CSV/XLSX files and normalized row JSONL for text projects
|       |-- text_workbook.json         # Frozen text source/mapping selection
|       |-- text_sheets/               # Ordered prompt/model sheets for the text workbook
|       |-- structured_sources/       # Reusable primary-PDF/supporting-file bundles for structured projects
|       |-- structured_workbooks/     # Ordered structured workbook metadata
|       |-- structured_sheets/        # Workbook-owned schemas, parsed rows, and parse errors
|       |-- jobs/                     # PDF jobs or text row jobs
|       |-- *_rq_screening_summary.xlsx
|       |-- cerebro_*_text_extraction_export.xlsx
|       `-- cerebro_*_structured_pdf_export.xlsx
|-- prompts/                          # Saved prompt files
`-- queue_state.json                  # Global queue pause/resume state
```

These runtime files are not committed.

### PDF Study Bundles

Standard and structured PDF dashboards treat one primary PDF plus any supporting files as one study bundle and create one job for that bundle. The primary PDF remains at `input/uploaded.pdf` for compatibility. Supporting sources are stored under `input/attachments/`, while ordered file details and hashes are stored in `metadata.json` as `source_files`.

- Supporting file types are PDF, XLSX, and CSV.
- Folder upload automatically pairs sources with the same normalized study name; the intake review provides a selector for ambiguous or unmatched files.
- Local OCR processes the primary and supporting PDFs, and creates bounded text transcripts for supporting XLSX/CSV files before the model prompt is built.
- OpenAI PDF-file mode sends all files in the bundle as one request.
- Duplicate checks, OCR reuse, OpenAI file reuse, and rerun children are scoped to the complete bundle hash so a paper cannot be confused with the same paper plus different supplementary material.

On startup, existing jobs still under `data/jobs/` are copied into the default `Legacy jobs` project. The migration is idempotent and leaves the original legacy folders in place.

Text projects use a workbook interface after source upload. The project column mapping is frozen and reproduced across every sheet. Each sheet has its own prompt, model configuration, jobs, status counts, and outputs. A sheet locks on its first run; duplicating it copies the configuration immediately to the right without copying jobs or results. The on-screen spreadsheet shows only mapped input columns. `Export worksheet` downloads the selected sheet only, while `Export workbook` creates one worksheet per extraction sheet; both include every original source column plus CEREBRO result columns.

## 3. Structured PDF Extraction

Structured PDF projects add a workbook-style extraction mode for PDFs.

The structured dashboard has two workspace tabs:

1. `PDF library`: import primary PDFs and optional supporting files once at the project level. Imported study bundles can be reused by every workbook in the project.
2. `Workbooks`: choose or create a workbook, configure its worksheet schemas, select library sources, run extraction, review results, and export the active workbook.

The spreadsheet grid is the main schema surface:

- A structured project can contain several workbooks. Each workbook has its own ordered sheet tabs, and the `+` button creates another sheet in the active workbook.
- `Duplicate workbook` copies the active workbook's editable sheet schemas into a new workbook in the same project, without jobs, rows, errors, or locks. `Duplicate project` retains the earlier cross-project schema-copy workflow.
- The sheet name, context, and `More information / other preferences` fields sit above the grid.
- Users name active columns directly in the spreadsheet header.
- Every active column generates a matching instruction card below the grid with:
  - Column name.
  - Question.
  - Rules / expected values / examples.
- The grid also shows inactive light-gray columns to the right, so the surface reads like a full spreadsheet rather than only the configured columns.
- Hovering over the separator after the last active column shows a blue vertical line and a small plus circle. Clicking it adds a new active column and focuses its header cell.
- Rows are rendered in a fixed-height virtualized grid, so the page does not grow with every parsed result.
- The grid shows queued/running structured PDF jobs immediately with source PDF, parse status, and parse date, then refreshes those rows as status changes.
- Users can click `Paste sheet / columns` to import either columns only or a full sheet definition containing sheet name, context, more information / preferences, and columns.
- `Export all sheet prompts` downloads every sheet's editable copy/paste definition from the active workbook in workbook order as one text file. It excludes compiled TSV and model instructions.
- If imported text would overwrite existing fields or columns, CEREBRO shows one conflict prompt listing all affected items.
- Structured sheets autosave while editing, so users do not need to click `Save sheet` after every change.
- A sheet locks when its first structured extraction run is queued. Locked sheets are read-only; users duplicate the sheet to edit the schema without copying extracted rows or parse errors.
- Existing structured projects are migrated lazily and safely: their current sheets remain in place and are assigned to a default `Workbook 1`. Existing rows, errors, job folders, and sheet ids are not moved or rerun.

CEREBRO compiles the structured sheet into a strict TSV prompt. The sheet schema is the source of truth: users do not manually write the TSV header. The backend requires the model response to start with the exact configured tab-separated header, parses rows into JSON, preserves raw output, and records parse errors separately.

Structured project storage:

```text
data/projects/<project_id>/
|-- structured_sources/
|   `-- <source_id>/
|       |-- source.json
|       `-- input/
|           |-- uploaded.pdf
|           `-- attachments/
|-- structured_workbooks/
|   `-- <workbook_id>/
|       `-- workbook.json
|-- structured_sheets/
|   `-- <sheet_id>/
|       |-- sheet.json
|       |-- rows.jsonl
|       `-- errors.jsonl
`-- jobs/
    `-- <job_id>/
        |-- metadata.json
        |-- status.json
        `-- outputs/
            |-- structured_raw_response.tsv
            |-- structured_parsed_rows.json
            `-- structured_parse_errors.json
```

Structured export creates one Excel worksheet per sheet in the active workbook and includes provenance columns such as source PDF, job id, model, parse status, and parse error before the sheet-defined columns. `Export worksheet` downloads only the currently selected sheet, while `Export active workbook` exports all sheets in the selected workbook.

## 4. How To Deploy Locally

Clone the repository:

```bash
git clone https://github.com/gabsbarreto/CEREBRO.git
cd CEREBRO
```

Create and activate a Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional OpenAI setup:

```bash
export OPENAI_API_KEY="sk-..."
```

OpenAI-backed queues allow 15 simultaneous requests by default. Override this when needed with `MAX_OPENAI_CONCURRENT_REQUESTS`.

You can also paste the OpenAI API key into the browser UI, or place it in:

```text
data/api_key.txt
```

Optional local OCR/model setup:

```bash
export DEEPSEEK_OCR_MODEL_PATH="/path/to/deepseek-ocr-model"
export DEEPSEEK_OCR_PYTHON="/path/to/python/with/deepseekocr2"
```

To search for a local DeepSeekOCR2 model:

```bash
python scripts/find_deepseek_ocr.py
```

Run the app:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

For development, keep reload watching code only. Runtime project data changes
frequently while jobs run and must not trigger an application reload:

```bash
uvicorn app.main:app --reload --reload-exclude 'data/**' --host 127.0.0.1 --port 8001
```

On startup, CEREBRO restores durable queues in the background. Large text
projects first rebuild a local lightweight row index, so the server and UI stay
available while the queue is being restored.

Open:

```text
http://127.0.0.1:8001/
```

The app creates `data/`, `data/jobs/`, `data/projects/`, and `data/prompts/` automatically when needed.

## 5. Licensing

CEREBRO is licensed under the GNU General Public License v3.0.

See [LICENSE](LICENSE) for the full license text.
