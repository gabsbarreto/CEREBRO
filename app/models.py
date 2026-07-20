from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app import config

QWEN35_9B_PRESET: dict[str, Any] = {
    "label": "Qwen3.5 9B 8-bit (reasoning)",
    "rq_provider": "local",
    "rq_screening_model": config.RQ_SCREENING_MODEL,
    "rq_max_tokens": config.RQ_SCREENING_MAX_TOKENS,
    "rq_thinking_budget": config.RQ_SCREENING_THINKING_BUDGET,
    "rq_enable_thinking": True,
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "qwen35_9b_8bit_reasoning": QWEN35_9B_PRESET,
    "qwen36_27b_instruct": {
        **QWEN35_9B_PRESET,
        "public": False,
    },
    "openai_gpt5_mini_high": {
        "label": "OpenAI gpt-5 mini (high reasoning)",
        "rq_provider": "openai",
        "rq_screening_model": "gpt-5-mini",
        "rq_max_tokens": config.OPENAI_RQ_SCREENING_MAX_TOKENS,
        "rq_enable_thinking": True,
        "openai_reasoning_effort": "high",
    },
    "openai_gpt54_mini_high": {
        "label": "OpenAI gpt-5.4 mini (high reasoning)",
        "rq_provider": "openai",
        "rq_screening_model": "gpt-5.4-mini",
        "rq_max_tokens": config.OPENAI_RQ_SCREENING_MAX_TOKENS,
        "rq_enable_thinking": True,
        "openai_reasoning_effort": "high",
    },
}


@dataclass
class JobStatus:
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Queued"
    progress: float = 0.0
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["progress"] = max(0.0, min(1.0, float(self.progress)))
        return payload


@dataclass
class JobSettings:
    ocr_dpi: int = config.DEFAULT_OCR_DPI
    ocr_batch_size: int = config.DEFAULT_OCR_BATCH_SIZE
    deepseek_ocr_model_path: str = ""
    rq_model_preset: str = "qwen35_9b_8bit_reasoning"
    rq_provider: str = config.RQ_SCREENING_PROVIDER
    rq_screening_model: str = config.RQ_SCREENING_MODEL
    rq_max_tokens: int = config.RQ_SCREENING_MAX_TOKENS
    rq_thinking_budget: int = config.RQ_SCREENING_THINKING_BUDGET
    rq_temperature: float = config.RQ_SCREENING_TEMPERATURE
    rq_top_p: float = config.RQ_SCREENING_TOP_P
    rq_top_k: int = config.RQ_SCREENING_TOP_K
    rq_min_p: float = config.RQ_SCREENING_MIN_P
    rq_presence_penalty: float = config.RQ_SCREENING_PRESENCE_PENALTY
    rq_repetition_penalty: float = config.RQ_SCREENING_REPETITION_PENALTY
    rq_enable_thinking: bool = config.RQ_SCREENING_ENABLE_THINKING
    rq_local_inference_verbose: bool = config.RQ_LOCAL_INFERENCE_VERBOSE
    openai_reasoning_effort: str = config.OPENAI_REASONING_EFFORT
    openai_input_mode: str = "ocr_text"
    openai_api_key: str = ""
    rq_prompt_filename: str = config.DEFAULT_RQ_PROMPT_FILENAME
    rq_system_prompt: str = ""

    @classmethod
    def from_form(cls, form: dict[str, Any]) -> "JobSettings":
        form = dict(form)
        preset_id = str(form.get("rq_model_preset") or "").strip()
        preset = MODEL_PRESETS.get(preset_id)
        if preset is not None:
            form.update(preset)
            form["rq_model_preset"] = preset_id
        model = str(form.get("rq_screening_model") or config.RQ_SCREENING_MODEL).strip()
        provider = normalize_provider(str(form.get("rq_provider") or "").strip(), model)
        enable_thinking = _bool(form.get("rq_enable_thinking"), config.RQ_SCREENING_ENABLE_THINKING)
        settings = cls(
            ocr_dpi=_int(form.get("ocr_dpi"), config.DEFAULT_OCR_DPI),
            ocr_batch_size=max(1, _int(form.get("ocr_batch_size"), config.DEFAULT_OCR_BATCH_SIZE)),
            deepseek_ocr_model_path=str(form.get("deepseek_ocr_model_path") or "").strip(),
            rq_model_preset=preset_id or preset_id_for_model(provider, model),
            rq_provider=provider,
            rq_screening_model=model,
            rq_max_tokens=_int(form.get("rq_max_tokens"), config.RQ_SCREENING_MAX_TOKENS),
            rq_thinking_budget=_int(form.get("rq_thinking_budget"), config.RQ_SCREENING_THINKING_BUDGET),
            rq_temperature=_float(form.get("rq_temperature"), config.RQ_SCREENING_TEMPERATURE),
            rq_top_p=_float(form.get("rq_top_p"), config.RQ_SCREENING_TOP_P),
            rq_top_k=_int(form.get("rq_top_k"), config.RQ_SCREENING_TOP_K),
            rq_min_p=_float(form.get("rq_min_p"), config.RQ_SCREENING_MIN_P),
            rq_presence_penalty=_float(form.get("rq_presence_penalty"), config.RQ_SCREENING_PRESENCE_PENALTY),
            rq_repetition_penalty=_float(form.get("rq_repetition_penalty"), config.RQ_SCREENING_REPETITION_PENALTY),
            rq_enable_thinking=enable_thinking,
            rq_local_inference_verbose=_bool(form.get("rq_local_inference_verbose"), config.RQ_LOCAL_INFERENCE_VERBOSE),
            openai_reasoning_effort=str(form.get("openai_reasoning_effort") or config.OPENAI_REASONING_EFFORT).strip(),
            openai_input_mode=normalize_openai_input_mode(str(form.get("openai_input_mode") or "ocr_text"))
            if provider == "openai"
            else "ocr_text",
            openai_api_key=str(form.get("openai_api_key") or "").strip(),
            rq_prompt_filename=str(form.get("rq_prompt_filename") or config.DEFAULT_RQ_PROMPT_FILENAME).strip(),
            rq_system_prompt=str(form.get("rq_system_prompt") or "").strip(),
        )
        preset = qwen_generation_preset(model, enable_thinking) if provider == "local" else None
        if preset is not None:
            settings.rq_temperature = preset["rq_temperature"]
            settings.rq_top_p = preset["rq_top_p"]
            settings.rq_top_k = preset["rq_top_k"]
            settings.rq_min_p = preset["rq_min_p"]
            settings.rq_presence_penalty = preset["rq_presence_penalty"]
            settings.rq_repetition_penalty = preset["rq_repetition_penalty"]
            settings.rq_thinking_budget = int(preset.get("rq_thinking_budget", settings.rq_thinking_budget))
        return settings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_metadata_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        api_key_provided = bool(str(payload.pop("openai_api_key", "") or "").strip())
        payload["openai_api_key_provided"] = api_key_provided
        return payload


def qwen_generation_preset(model: str, enable_thinking: bool) -> dict[str, float | int] | None:
    normalized = str(model or "").lower()
    is_qwen35_9b = "qwen3.5" in normalized and ("9b" in normalized or "9-b" in normalized)
    if is_qwen35_9b:
        return {
            "rq_temperature": 1.0,
            "rq_top_p": 0.95,
            "rq_top_k": 20,
            "rq_min_p": 0.0,
            "rq_presence_penalty": 1.5,
            "rq_repetition_penalty": 1.0,
            "rq_thinking_budget": config.RQ_SCREENING_THINKING_BUDGET,
        }

    is_qwen36_27b = "qwen3.6" in normalized and ("27b" in normalized or "27-b" in normalized)
    if not is_qwen36_27b:
        return None

    if enable_thinking:
        return {
            "rq_temperature": 1.0,
            "rq_top_p": 0.95,
            "rq_top_k": 20,
            "rq_min_p": 0.0,
            "rq_presence_penalty": 0.0,
            "rq_repetition_penalty": 1.0,
            "rq_thinking_budget": config.RQ_SCREENING_THINKING_BUDGET,
        }
    return {
        "rq_temperature": 0.7,
        "rq_top_p": 0.8,
        "rq_top_k": 20,
        "rq_min_p": 0.0,
        "rq_presence_penalty": 1.5,
        "rq_repetition_penalty": 1.0,
        "rq_thinking_budget": config.RQ_SCREENING_THINKING_BUDGET,
    }


def normalize_provider(provider: str, model: str) -> str:
    provider = provider.strip().lower()
    if provider in {"local", "openai"}:
        return provider
    normalized_model = str(model or "").lower()
    if normalized_model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return config.RQ_SCREENING_PROVIDER


def normalize_openai_input_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"pdf_file", "file", "openai_file", "direct_pdf"}:
        return "pdf_file"
    return "ocr_text"


def preset_id_for_model(provider: str, model: str) -> str:
    for preset_id, preset in MODEL_PRESETS.items():
        if preset["rq_provider"] == provider and preset["rq_screening_model"] == model:
            return preset_id
    return "qwen35_9b_8bit_reasoning"


def public_model_presets() -> list[dict[str, Any]]:
    presets: list[dict[str, Any]] = []
    for preset_id, preset in MODEL_PRESETS.items():
        if preset.get("public") is False:
            continue
        settings = JobSettings.from_form({"rq_model_preset": preset_id})
        presets.append(
            {
                "id": preset_id,
                "label": preset["label"],
                "settings": {
                    "provider": settings.rq_provider,
                    "model": settings.rq_screening_model,
                    "max_tokens": settings.rq_max_tokens,
                    "thinking_budget": settings.rq_thinking_budget,
                    "reasoning": settings.rq_enable_thinking,
                    "temperature": settings.rq_temperature,
                    "top_p": settings.rq_top_p,
                    "top_k": settings.rq_top_k,
                    "min_p": settings.rq_min_p,
                    "presence_penalty": settings.rq_presence_penalty,
                    "repetition_penalty": settings.rq_repetition_penalty,
                    "openai_reasoning_effort": settings.openai_reasoning_effort,
                    "openai_input_mode": settings.openai_input_mode,
                },
            }
        )
    return presets


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
