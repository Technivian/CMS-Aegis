"""Prompt policy checks for internal AI assistant endpoints."""

from __future__ import annotations

import re


MAX_PROMPT_LENGTH = 2000
_BLOCK_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"print\s+(all\s+)?(secrets|tokens|credentials)", re.IGNORECASE),
    re.compile(r"bypass\s+(policy|guardrails|security)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(developer|system)", re.IGNORECASE),
    re.compile(r"exfiltrat(e|ion)", re.IGNORECASE),
)


def evaluate_prompt(prompt: str) -> dict:
    normalized = (prompt or "").strip()
    if not normalized:
        return {
            "allowed": True,
            "reason": "default_prompt",
            "normalized_prompt": "",
        }

    if len(normalized) > MAX_PROMPT_LENGTH:
        return {
            "allowed": False,
            "reason": "prompt_too_long",
            "normalized_prompt": normalized[:MAX_PROMPT_LENGTH],
        }

    for pattern in _BLOCK_PATTERNS:
        if pattern.search(normalized):
            return {
                "allowed": False,
                "reason": "prompt_injection_detected",
                "normalized_prompt": normalized,
            }

    return {
        "allowed": True,
        "reason": "ok",
        "normalized_prompt": normalized,
    }
