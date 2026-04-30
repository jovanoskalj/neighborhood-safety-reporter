import json
from functools import lru_cache

import requests
from django.conf import settings

from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

VALID_CATEGORIES = {"infrastructure", "utilities", "safety", "health", "other"}
VALID_PRIORITIES = {"urgent", "normal", "low"}
VALID_SECTORS = {"infrastructure", "utilities", "safety", "health", "admin"}

SAFETY_KEYWORDS = {
    "напад", "насил", "тепач", "краж", "краде", "крадци", "разбој", "сомнител",
    "закана", "полици", "криминал", "ограб", "убиств", "дрога",
}
HEALTH_KEYWORDS = {
    "болниц", "клиник", "амбулант", "здрав", "здравје", "епидем", "зараза", "инфек",
    "санитар", "лекар", "аптека",
}
UTILITIES_KEYWORDS = {
    "ѓубре", "контејнер", "депони", "канализа", "шахта", "одвод", "вода", "истекува",
    "поплав", "смет", "комунал", "хигиен",
}
INFRASTRUCTURE_KEYWORDS = {
    "дупка", "асфалт", "тротоар", "улиц", "пат", "коловоз", "семафор", "осветлува",
    "светилк", "улично светло", "мост", "знак", "инфраструкт",
}

URGENT_KEYWORDS = {
    "итно", "небезбед", "опас", "ризик", "повред", "деца", "училиш", "пожар", "насил",
    "краж", "краде", "судир", "излева", "поплав",
}
LOW_KEYWORDS = {"мала", "мал", "козмет", "естет", "не е итно", "кога можете"}


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


def _parse_json_text(result_text: str) -> dict:
    """Parse JSON with light cleanup for fenced/verbose model output."""
    cleaned = (result_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


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


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _heuristic_classify(description: str) -> dict[str, str] | None:
    """Deterministic keyword routing for MK/EN local complaints."""
    text = (description or "").strip().lower()
    if not text:
        return None

    if _contains_any(text, SAFETY_KEYWORDS):
        category = "safety"
        sector = "safety"
    elif _contains_any(text, HEALTH_KEYWORDS):
        category = "health"
        sector = "health"
    elif _contains_any(text, UTILITIES_KEYWORDS):
        category = "utilities"
        sector = "utilities"
    elif _contains_any(text, INFRASTRUCTURE_KEYWORDS):
        category = "infrastructure"
        sector = "infrastructure"
    else:
        return None

    # Handle explicit negation first (e.g. "не е итно")
    if "не е итно" in text or "not urgent" in text:
        priority = "low"
    elif _contains_any(text, URGENT_KEYWORDS):
        priority = "urgent"
    elif _contains_any(text, LOW_KEYWORDS):
        priority = "low"
    else:
        priority = "normal"

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
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=settings.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        result_text = _extract_json_payload(response.json())

        raw_data = _parse_json_text(result_text)
        return _validate_result(raw_data)
    except Exception:
        return _fallback()


def classify_report(description: str) -> dict[str, str]:
    """Classify a report description into category, priority, and sector."""
    normalized_description = (description or "").strip()
    if not normalized_description:
        return _fallback()

    heuristic_result = _heuristic_classify(normalized_description)
    if heuristic_result:
        return heuristic_result

    return _classify_description(normalized_description)