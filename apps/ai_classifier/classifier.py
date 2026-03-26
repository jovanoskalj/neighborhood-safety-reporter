import json
import requests
from functools import lru_cache
from django.conf import settings 
from apps.ai_classifier.prompts import CLASSIFICATION_PROMPT

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL

def classify_report(report):
    """
    Stub for AI classification using Ollama
    Returns a dict with category, priority, sector
    """
    
     # Hardcoded description for testing
    description = "Streetlight not working in front of main library"

    prompt = CLASSIFICATION_PROMPT.format(description=description)


    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": "llama3/mistral", "prompt": prompt},
            timeout=10
        )
        response.raise_for_status()
        result_text = response.json().get("completion", "")

        classification = json.loads(result_text)
        # Ensure keys exist
        for key in ["category", "priority", "sector"]:
            if key not in classification:
                raise ValueError(f"Missing key {key} in classification")
        return classification

    except Exception as e:
        print(f"Classification failed for: {description}. Error: {e}")
        return {
            "category": "unclassified",
            "priority": "unclassified",
            "sector": "unclassified"
        }