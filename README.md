# Local RQ Screening App

Browser-based app for PDF upload, page rendering, DeepSeekOCR2 OCR, merged full text, and RQ screening.

OCR always runs locally. RQ screening can use a local MLX model or the OpenAI Responses API when you select the OpenAI preset and provide an API key.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If your DeepSeekOCR2 setup is in a separate Python environment, keep using that environment for OCR and set `DEEPSEEK_OCR_PYTHON`.

## Discover DeepSeekOCR2

```bash
python scripts/find_deepseek_ocr.py
```

The app searches:

- `DEEPSEEK_OCR_MODEL_PATH`
- `DEEPSEEK_OCR_PYTHON`
- `~/.cache/huggingface/hub`
- `~/.cache/modelscope`
- `~/.cache/mlx`
- `~/Library/Caches/huggingface`
- `/Users/ha25082/Library/CloudStorage/OneDrive-UniversityofBristol/Documents/Translation Project`
- likely model/cache folders inside the Translation Project

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

or:

```text
http://127.0.0.1:8000/rq-screening
```

The browser UI can add several PDFs to the queue at once. Use **PDF uploads** for one or more selected files, or **PDF folder** to add all PDFs from a local folder. Browser folder upload uses the standard Chromium/Safari `webkitdirectory` picker. Jobs are queued and processed sequentially. If you refresh the page, the queue display is restored from `data/jobs/`; jobs still marked `queued` on server startup are put back into the processing queue.

Before queueing uploads, the app checks existing `metadata.json` files for completed jobs with the same PDF filename. If a PDF has already been screened, the browser asks whether to keep it anyway. Choosing **No** queues only new PDFs. Choosing **Yes** queues the existing job again, reuses its saved OCR text, and overwrites the previous RQ screening prompt/output with a fresh LLM screening run.

Queue controls:

- **Pause queue** pauses dispatch, interrupts the active OCR/LLM subprocess, and returns that job to the front of the queue.
- **Resume run** restarts processing from the front of the queue using the model preset currently selected in the form.
- **Reallocate failed** puts failed jobs back into the queue for retry using the selected model preset, and updates each retried job's metadata with that preset.
- **Clean queue** removes queued jobs from the queue and deletes their job folders so they disappear from the jobs list.

## Environment Variables

```bash
export DEEPSEEK_OCR_MODEL_PATH="/path/to/local/deepseekocr2"
export DEEPSEEK_OCR_PYTHON="/path/to/python/with/deepseekocr2"
export RQ_SCREENING_MODEL="leonsarmiento/Qwen3.6-27B-3bit-mlx"
export RQ_SCREENING_TOP_K="20"
export RQ_SCREENING_MIN_P="0.0"
export RQ_SCREENING_PRESENCE_PENALTY="0.0"
export RQ_SCREENING_REPETITION_PENALTY="1.0"
export OPENAI_API_KEY="sk-..."
export OPENAI_REASONING_EFFORT="high"
export OPENAI_RQ_SCREENING_MAX_TOKENS="80000"
```

DeepSeek OCR defaults to the local MLX model:

```text
mlx-community/DeepSeek-OCR-2-8bit
```

Auto-detection prefers the cached 8-bit snapshot under:

```text
~/.cache/huggingface/hub/models--mlx-community--DeepSeek-OCR-2-8bit
```

The default RQ screening preset is:

- model: `leonsarmiento/Qwen3.6-27B-3bit-mlx`
- max new tokens: `10000` for local Qwen, `80000` for OpenAI reasoning by default
- thinking/reasoning: disabled

The browser exposes model selection as a dropdown. Generation parameters are backend presets and are shown read-only in the UI:

- `Qwen3.6 27B`
- `OpenAI gpt-5 mini (high reasoning)`
- `OpenAI gpt-5.4 mini (high reasoning)`

Qwen screening preset:

| Model | Mode | Temperature | Top p | Top k | Min p | Presence penalty | Repetition penalty |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `leonsarmiento/Qwen3.6-27B-3bit-mlx` | non-thinking | 0.7 | 0.8 | 20 | 0.0 | 1.5 | 1.0 |

The OpenAI presets use max output tokens `80000` and high reasoning effort. Selecting an OpenAI preset in the browser reveals an API key field and an OpenAI PDF handling selector. The key is passed to the worker for that run and is not written into job metadata. You can also set `OPENAI_API_KEY` in the terminal before starting the app, or place the key in `data/api_key.txt`. Key priority is browser field, then `OPENAI_API_KEY`, then `data/api_key.txt`.

OpenAI PDF handling modes:

- `Send PDF file directly to OpenAI`: skips local OCR, uploads the PDF to OpenAI with `purpose="user_data"`, and sends the resulting `file_id` with the system prompt. The returned `openai_file_id` is stored in job metadata and reused for future jobs with the same PDF.
- `Use local OCR text`: preserves the previous behavior by running local DeepSeekOCR2 OCR and sending the merged text to OpenAI.

Each OpenAI run saves debugging artifacts in the job `outputs/` folder:

- `openai_request.json`
- `openai_response.json`

If the Responses API returns no final text, the job is marked failed instead of writing an empty spreadsheet row. Check `openai_response.json` and `status.json`; an `incomplete_details.reason` of `max_output_tokens` means the model spent the output budget before producing a final answer.

## Job Folders

Each run is saved under:

```text
data/jobs/{job_id}/
```

with:

```text
input/uploaded.pdf
rendered_pages/page_0001.png
ocr_images/page_0001.jpg
ocr_text/page_0001.md
outputs/merged_full_text.txt
outputs/rq_prompt.txt
outputs/rq_screening_output.md
outputs/openai_request.json
outputs/openai_response.json
metadata.json
status.json
```

## Excel Summary

After each successful full run, meaning OCR plus RQ LLM inference, the app appends one row to:

```text
data/rq_screening_summary.xlsx
```

Use **Download Excel report** in the browser to rebuild this workbook from all completed job folders and download it.

The workbook is append-only and contains:

- `job_id`
- `filename`
- `when it was inferenced`
- `how long it took`
- `LLM model`
- `LLM output`

Set a different summary path with:

```bash
export RQ_SCREENING_SUMMARY_XLSX="/path/to/rq_screening_summary.xlsx"
```

## Troubleshooting

If DeepSeekOCR2 is not found, run `python scripts/find_deepseek_ocr.py`, then paste the best candidate path into the UI or set `DEEPSEEK_OCR_MODEL_PATH`.

If OCR dependency loading fails, set `DEEPSEEK_OCR_PYTHON` to the Python executable from the environment where `mlx-vlm` and DeepSeekOCR2 work.

If MLX runs out of memory, close other memory-heavy apps, lower OCR DPI, reduce max new tokens, or choose a smaller local MLX screening model.

If OCR output is empty, inspect `data/jobs/{job_id}/rendered_pages/`, `ocr_images/`, and `ocr_text/`. Try a higher OCR DPI or paste a known-good DeepSeekOCR2 model path.

Batch OCR is accepted as a setting, but the DeepSeekOCR2 worker currently processes one page at a time because the inspected local worker uses single-image `mlx_vlm.generate` calls. If a batch-safe local DeepSeekOCR2 path is added later, `scripts/deepseek_ocr_worker.py` is the place to wire it.

The OCR prompt follows the DeepSeek OCR vLLM recipe's plain prompt style:

```text
<image>
 Free OCR.
```

## Overnight Batch Runs

For unattended runs, use the sequential batch runner. It creates the same `data/jobs/{job_id}/` folders as the browser UI and processes one PDF at a time so model memory is released between jobs.

Run every PDF in a folder:

```bash
python scripts/run_batch.py --pdf-dir "/path/to/pdfs"
```

Run recursively:

```bash
python scripts/run_batch.py --pdf-dir "/path/to/pdfs" --recursive
```

Run from a text file containing one PDF path per line:

```bash
python scripts/run_batch.py --file-list "/path/to/pdf-list.txt"
```

Keep watching a folder for new PDFs until you stop it with `Ctrl+C`:

```bash
python scripts/run_batch.py --pdf-dir "/path/to/inbox" --watch --poll-seconds 60
```

Useful overnight options:

```bash
python scripts/run_batch.py \
  --pdf-dir "/path/to/pdfs" \
  --recursive \
  --ocr-dpi 100 \
  --rq-max-tokens 30000
```
