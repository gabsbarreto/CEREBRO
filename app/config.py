from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
SUMMARY_XLSX_PATH = Path(os.getenv("RQ_SCREENING_SUMMARY_XLSX", str(DATA_DIR / "rq_screening_summary.xlsx")))
PROMPTS_DIR = Path(os.getenv("RQ_SCREENING_PROMPTS_DIR", str(DATA_DIR / "prompts")))
DEFAULT_RQ_PROMPT_FILENAME = os.getenv("DEFAULT_RQ_PROMPT_FILENAME", "Animal_studies_1.txt")
RQ_PROMPT_TEMPLATE_PATH = PROMPTS_DIR / DEFAULT_RQ_PROMPT_FILENAME
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

TRANSLATION_PROJECT_DIR = Path(
    "/Users/ha25082/Library/CloudStorage/OneDrive-UniversityofBristol/Documents/Translation Project"
)

DEFAULT_OCR_DPI = int(os.getenv("DEFAULT_OCR_DPI", "100"))
DEFAULT_OCR_BATCH_SIZE = int(os.getenv("DEFAULT_OCR_BATCH_SIZE", "1"))
DEFAULT_DEEPSEEK_OCR_MODEL = os.getenv("DEEPSEEK_OCR_MODEL", "mlx-community/DeepSeek-OCR-2-8bit")
DEFAULT_DEEPSEEK_OCR_MAX_TOKENS = int(os.getenv("DEEPSEEK_OCR_MAX_TOKENS", "4096"))
DEFAULT_DEEPSEEK_OCR_TEMPERATURE = float(os.getenv("DEEPSEEK_OCR_TEMPERATURE", "0.0"))
DEFAULT_DEEPSEEK_OCR_PROMPT = os.getenv(
    "DEEPSEEK_OCR_PROMPT",
    "<image>\n Free OCR.",
)

QWEN35_9B_8BIT_MODEL_PATH = Path(
    os.getenv(
        "QWEN35_9B_8BIT_MODEL_PATH",
        "/Users/ha25082/.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-8bit/"
        "snapshots/16daa4818c54ce5f5436f929d52542eb65bbed9d",
    )
)

RQ_SCREENING_PROVIDER = os.getenv("RQ_SCREENING_PROVIDER", "local")
RQ_SCREENING_MODEL = os.getenv("RQ_SCREENING_MODEL", str(QWEN35_9B_8BIT_MODEL_PATH))
RQ_SCREENING_MAX_TOKENS = int(os.getenv("RQ_SCREENING_MAX_TOKENS", "12000"))
RQ_SCREENING_THINKING_BUDGET = int(os.getenv("RQ_SCREENING_THINKING_BUDGET", "10000"))
OPENAI_RQ_SCREENING_MAX_TOKENS = int(os.getenv("OPENAI_RQ_SCREENING_MAX_TOKENS", "80000"))
RQ_SCREENING_TEMPERATURE = float(os.getenv("RQ_SCREENING_TEMPERATURE", "1.0"))
RQ_SCREENING_TOP_P = float(os.getenv("RQ_SCREENING_TOP_P", "0.95"))
RQ_SCREENING_TOP_K = int(os.getenv("RQ_SCREENING_TOP_K", "20"))
RQ_SCREENING_MIN_P = float(os.getenv("RQ_SCREENING_MIN_P", "0.0"))
RQ_SCREENING_PRESENCE_PENALTY = float(os.getenv("RQ_SCREENING_PRESENCE_PENALTY", "1.5"))
RQ_SCREENING_REPETITION_PENALTY = float(os.getenv("RQ_SCREENING_REPETITION_PENALTY", "1.0"))
RQ_SCREENING_ENABLE_THINKING = os.getenv("RQ_SCREENING_ENABLE_THINKING", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RQ_LOCAL_INFERENCE_VERBOSE = os.getenv("RQ_LOCAL_INFERENCE_VERBOSE", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high")
MAX_OPENAI_CONCURRENT_REQUESTS = max(
    1,
    int(os.getenv("MAX_OPENAI_CONCURRENT_REQUESTS", os.getenv("RQ_MAX_OPENAI_CONCURRENT_REQUESTS", "5"))),
)
MAX_OCR_WORKERS = max(1, int(os.getenv("MAX_OCR_WORKERS", os.getenv("RQ_MAX_OCR_WORKERS", "1"))))
OPENAI_INFERENCE_MAX_RETRIES = max(0, int(os.getenv("OPENAI_INFERENCE_MAX_RETRIES", "3")))
OPENAI_INFERENCE_RETRY_BASE_SECONDS = max(0.1, float(os.getenv("OPENAI_INFERENCE_RETRY_BASE_SECONDS", "2.0")))

for directory in [DATA_DIR, JOBS_DIR, PROMPTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
