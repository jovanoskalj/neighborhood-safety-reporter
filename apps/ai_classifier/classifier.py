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
import requests
from django.conf import settings
from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL


def classify_report(report):
    """
    Classifies a report using Ollama.
    Returns a dict with category, priority, sector.
    Raises an exception on failure so the caller can handle fallback.
    """
    description = report.get("description", "No description provided")
    prompt = CLASSIFICATION_PROMPT.format(description=description)

    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=10,
    )
    response.raise_for_status()

    result_text = response.json().get("response", "")
    classification = json.loads(result_text)

    for key in ["category", "priority", "sector"]:
        if key not in classification:
            raise ValueError(f"Missing key '{key}' in classification response")

    return classification