import requests

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        },
        timeout=5
    )
    return response.json()


def generate_ai_summary(description):
    try:
        result = call_ollama(description)
        return result.get("response", "No AI output")

    except requests.exceptions.Timeout:
        return "AI unavailable, using default summary"