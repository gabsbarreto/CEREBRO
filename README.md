# CEREBRO

CEREBRO is an AI-assisted scientific data extraction tool for PDFs.

Users upload one PDF or a folder of PDFs, write an extraction prompt, choose a model, and send files to a processing queue. The app can process papers through either local OCR plus model extraction, or through OpenAI file/source extraction where the PDF is uploaded to OpenAI and used as source material.

## 1. What The App Does

CEREBRO helps screen and extract structured information from scientific papers.

Core workflow:

1. Upload PDFs individually or as a folder.
2. Choose a processing pathway:
   - OCR/text pathway: render PDF pages, run local OCR, merge text, then send the text to a local model or OpenAI model.
   - OpenAI file/source pathway: upload the PDF to OpenAI and send the file source with the extraction prompt.
3. Choose a model preset.
4. Provide an OpenAI API key when using OpenAI models.
5. Write or load an extraction prompt.
6. Add files to the queue.
7. Monitor batch progress, retry failed jobs, view outputs, and download an Excel report.

The app stores runtime job data locally under `data/`. This includes uploaded PDFs, OCR text, OpenAI request/response logs, job metadata, queue state, and generated Excel reports. The `data/` folder is intentionally ignored by Git.

## 2. Structure

```text
CEREBRO/
|-- app/
|   |-- main.py                       # FastAPI routes and app entrypoint
|   |-- config.py                     # Runtime configuration and environment defaults
|   |-- models.py                     # Job settings, model presets, and status models
|   |-- services/
|   |   |-- rq_screening_pipeline.py  # Main PDF processing pipeline
|   |   |-- job_queue.py              # Queue, pause/resume, retry, cleanup
|   |   |-- jobs.py                   # Job folders, metadata, and status files
|   |   |-- renderer.py               # PDF page rendering
|   |   |-- deepseek_ocr.py           # DeepSeek OCR integration
|   |   |-- openai_rq.py              # OpenAI Responses API calls
|   |   |-- openai_inference_queue.py # Parallel OpenAI inference queue
|   |   |-- rq_prompt.py              # Prompt loading/saving/building
|   |   `-- excel_summary.py          # Excel report generation
|   |-- static/
|   |   |-- styles.css                # CEREBRO UI styling
|   |   `-- rq_screening.js           # Browser UI behaviour
|   `-- templates/
|       `-- rq_screening.html         # Main dashboard page
|-- scripts/                          # Worker and batch helper scripts
|-- tests/                            # Backend/unit smoke tests
|-- CEREBRO_UI_IDENTITY.md            # UI identity and contribution notes
|-- requirements.txt                  # Python dependencies
|-- LICENSE                           # GPL-3.0 license
`-- README.md
```

Runtime-only folders/files:

```text
data/
|-- api_key.txt                       # Optional local OpenAI key file
|-- jobs/                             # Uploaded PDFs, OCR, outputs, metadata
|-- prompts/                          # Saved prompt files
|-- queue_state.json                  # Queue pause/resume state
`-- rq_screening_summary.xlsx         # Generated Excel report
```

These runtime files are not committed.

## 3. How To Deploy Locally

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
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/rq-screening
```

The app creates `data/`, `data/jobs/`, and `data/prompts/` automatically when needed.

## 4. Licensing

CEREBRO is licensed under the GNU General Public License v3.0.

See [LICENSE](LICENSE) for the full license text.
