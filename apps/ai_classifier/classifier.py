import json
from functools import lru_cache

import requests
from django.conf import settings

from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

VALID_CATEGORIES = {"infrastructure", "utilities", "safety", "health", "other"}
VALID_PRIORITIES = {"urgent", "normal", "low"}
VALID_SECTORS = {"infrastructure", "utilities", "safety", "health", "admin"}


def _fallback() -> dict[str, str]:
    """Return safe fallback classification for parsing/network failures."""
    return {
        "category": "other",
        "priority": "normal",
        "sector": "admin",
        "status": "unclassified",
    }


def _extract_json_payload(response_json: dict) -> str:
    """Extract model output text from Ollama API response."""
    return response_json.get("response") or response_json.get("completion") or ""


def _validate_result(result: dict) -> dict[str, str]:
    """Validate and normalize classifier output against accepted enums."""
    category = str(result.get("category", "other")).strip().lower()
    priority = str(result.get("priority", "normal")).strip().lower()
    sector = str(result.get("sector", "admin")).strip().lower()

    if category not in VALID_CATEGORIES or priority not in VALID_PRIORITIES or sector not in VALID_SECTORS:
        return _fallback()

    return {
        "category": category,
        "priority": priority,
        "sector": sector,
        "status": "new",
    }


@lru_cache(maxsize=512)
def _classify_description(description: str) -> dict[str, str]:
    """Call Ollama with timeout and parse JSON classification output."""
    prompt = CLASSIFICATION_PROMPT.format(description=description)

    try:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=5,
        )
        response.raise_for_status()
        result_text = _extract_json_payload(response.json())

        raw_data = json.loads(result_text)
        return _validate_result(raw_data)
    except Exception:
        return _fallback()


def classify_report(description: str) -> dict[str, str]:
    """Classify a report description into category, priority, and sector."""
    normalized_description = (description or "").strip()
    if not normalized_description:
        return _fallback()
    return _classify_description(normalized_description)