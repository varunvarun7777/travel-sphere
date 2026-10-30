"""Gemini (Google AI Studio) JSON calls over the REST API.

Configured with GEMINI_API_KEY and optionally GEMINI_MODELS, a comma-separated
list of models tried in order. When a model is overloaded, rate-limited, retired
or slow, the next one is tried; if all fail the caller falls back to the rules engine.
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx
from pydantic import BaseModel

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODELS = "gemini-3.5-flash,gemini-flash-latest,gemini-flash-lite-latest"
NEXT_MODEL_STATUSES = {404, 429, 500, 503}  # retired, rate-limited or overloaded
MAX_WAIT_S = 4.0
TIMEOUT_S = 25.0


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def models() -> list[str]:
    raw = os.getenv("GEMINI_MODELS") or os.getenv("GEMINI_MODEL") or DEFAULT_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


def model_name() -> str:
    return models()[0]


def _retry_wait(resp: httpx.Response) -> float:
    """Honour a short server RetryInfo/Retry-After before moving on; cap it so requests stay responsive."""
    wait = 0.5
    if resp.headers.get("retry-after", "").isdigit():
        wait = float(resp.headers["retry-after"])
    try:
        for detail in resp.json().get("error", {}).get("details", []):
            m = re.fullmatch(r"([\d.]+)s", str(detail.get("retryDelay", "")))
            if m:
                wait = float(m.group(1))
    except ValueError:
        pass
    return min(wait, MAX_WAIT_S)


def _extract_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise RuntimeError(f"Gemini returned no output ({reason})")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    # JSON mode should return bare JSON; strip a code fence defensively.
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def generate_json(system: str, user: str, output_model: type[BaseModel], timeout: float = TIMEOUT_S,
                  budget: float | None = None) -> BaseModel:
    """Try each model in turn. ``timeout`` applies to each model; ``budget`` caps the total seconds
    (serverless hosts stop a request after a fixed time, so the fallbacks must fit inside it)."""
    deadline = time.monotonic() + budget if budget else None
    schema = json.dumps(output_model.model_json_schema(), ensure_ascii=False)
    body = {
        "systemInstruction": {"parts": [{"text": f"{system}\n\nReply with JSON only, matching this JSON Schema:\n{schema}"}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    errors = []
    with httpx.Client(timeout=timeout) as client:
        for i, model in enumerate(models()):
            wait = timeout
            if deadline is not None:
                wait = min(timeout, deadline - time.monotonic())
                if wait < 3:
                    errors.append("out of time")
                    break
            try:
                resp = client.post(API_URL.format(model=model), headers=headers, json=body, timeout=wait)
            except httpx.TimeoutException:
                errors.append(f"{model}: timed out")
                continue
            if resp.status_code in NEXT_MODEL_STATUSES:
                errors.append(f"{model}: HTTP {resp.status_code}")
                if resp.status_code == 429 and i + 1 < len(models()):
                    time.sleep(_retry_wait(resp))
                continue
            resp.raise_for_status()
            return output_model.model_validate_json(_extract_text(resp.json()))
    raise RuntimeError("All Gemini models failed: " + "; ".join(errors))
