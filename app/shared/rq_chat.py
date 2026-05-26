from __future__ import annotations

import re
from typing import Any


def split_thinking(text: str) -> tuple[str, str, bool]:
    if "</think>" not in text:
        return "", text.strip(), False
    reasoning, final = text.split("</think>", 1)
    reasoning = reasoning.replace("<think>", "").strip()
    return reasoning, final.strip(), True


def strip_thinking(text: str) -> str:
    return re.sub(r"(?is)<think>.*?</think>", "", text).strip()


def combined_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "System instructions:\n"
        f"{system_prompt.strip()}\n\n"
        "User-provided text:\n"
        f"{user_prompt.strip()}\n"
    )


def build_chat_prompt(tokenizer: Any, system_prompt: str, user_prompt: str, enable_thinking: bool) -> str:
    if not hasattr(tokenizer, "apply_chat_template"):
        return combined_prompt(system_prompt, user_prompt)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=enable_thinking,
        )
    except TypeError:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        return combined_prompt(system_prompt, user_prompt)
