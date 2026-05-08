# import json
# import requests
# from functools import lru_cache
# from django.conf import settings 
# from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

# OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL

# def classify_report(report):
#     """
#     Stub for AI classification using Ollama
#     Returns a dict with category, priority, sector
#     """
    
#      # Hardcoded description for testing
#     description = report.get("description", "No description provided")

#     prompt = CLASSIFICATION_PROMPT.format(description=description)


#     try:
#         response = requests.post(
#             f"{OLLAMA_BASE_URL}/api/generate",
#             json={"model": "llava-llama3", "prompt": prompt},
#             timeout=10
#         )
#         response.raise_for_status()
#         result_text = response.json().get("completion", "")

#         classification = json.loads(result_text)
#         # Ensure keys exist
#         for key in ["category", "priority", "sector"]:
#             if key not in classification:
#                 raise ValueError(f"Missing key {key} in classification")
#         return classification

#     except Exception as e:
#         print(f"Classification failed for: {description}. Error: {e}")
#         return {
#             "category": "unclassified",
#             "priority": "unclassified",
#             "sector": "unclassified"
#         }

import json
import logging
from typing import Optional, Set
import requests
from django.conf import settings

from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

SAFETY_KEYWORDS = {
    "напад",
    "насил",
    "тепач",
    "краж",
    "краде",
    "крадци",
    "разбој",
    "сомнител",
    "закана",
    "полици",
    "криминал",
    "ограб",
    "убиств",
    "дрога",
}
HEALTH_KEYWORDS = {
    "болниц",
    "клиник",
    "амбулант",
    "здрав",
    "здравје",
    "епидем",
    "зараза",
    "инфек",
    "санитар",
    "лекар",
    "аптека",
}
UTILITIES_KEYWORDS = {
    "ѓубре",
    "контејнер",
    "депони",
    "канализа",
    "шахта",
    "одвод",
    "вода",
    "истекува",
    "поплав",
    "смет",
    "комунал",
    "хигиен",
}
INFRASTRUCTURE_KEYWORDS = {
    "дупка",
    "асфалт",
    "тротоар",
    "улиц",
    "пат",
    "коловоз",
    "семафор",
    "осветлува",
    "светилк",
    "улично светло",
    "мост",
    "знак",
    "инфраструкт",
}

URGENT_KEYWORDS = {
    "итно",
    "небезбед",
    "опас",
    "ризик",
    "повред",
    "деца",
    "училиш",
    "пожар",
    "насил",
    "краж",
    "краде",
    "кражби",
    "судир",
    "излева",
    "поплав",
    "поплавен",
    "семафор",
    "расипан",
    "ризично",
    "темно",
    "светилк",
    "нехигиен",
    "инфекц",
    "медицин",
    "отпад",
    "закани",
    "тепач",
}
LOW_KEYWORDS = {"мала", "мал", "козмет", "естет", "не е итно", "кога можете"}


def _fallback() -> dict:
    return {
        "category": "other",
        "priority": "normal",
        "sector": "admin",
        "status": "unclassified",
    }


def _contains_any(text: str, keywords: Set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _heuristic_classify(description: str) -> Optional[dict]:
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


def classify_report(report, timeout=10):
    """Classify a report description into category, priority, and sector."""
    if isinstance(report, str):
        description = report
    elif isinstance(report, dict):
        description = report.get("description", "")
    else:
        raise TypeError("classify_report expects a description string or a dict with 'description'.")

    normalized_description = (description or "").strip()
    if not normalized_description:
        return _fallback()

    heuristic_result = _heuristic_classify(normalized_description)
    if heuristic_result:
        return heuristic_result

    prompt = CLASSIFICATION_PROMPT.format(description=normalized_description)
    try:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        result_text = response.json().get("response") or response.json().get("completion") or "{}"
        classification = json.loads(result_text)
        for key in ["category", "priority", "sector"]:
            if key not in classification:
                raise ValueError(f"Missing key '{key}' in classification response")
        classification.setdefault("status", "new")
        return classification
    except Exception:
        logger.exception("AI classification failed; falling back to defaults.")
        return _fallback()
