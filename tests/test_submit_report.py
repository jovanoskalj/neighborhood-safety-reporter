import pytest
from unittest.mock import patch
from django.urls import reverse
import requests


@pytest.mark.django_db
def test_submit_report_with_ai(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    with patch("apps.reports.services.call_ollama") as mock_ollama:
        mock_ollama.return_value = {
            "response": "AI detected safety issue"
        }

        response = client.post(reverse("submit_report"), {
            "title": "Broken street light",
            "description": "Street light not working",
            "location": "Center",
            "latitude": 41.9973,
            "longitude": 21.4280
        })

    assert response.status_code in [200, 302]
    assert mock_ollama.called


@pytest.mark.django_db
def test_submit_report_ai_failure(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    with patch("apps.reports.services.call_ollama") as mock_ollama:
        mock_ollama.side_effect = requests.exceptions.Timeout

        response = client.post(reverse("submit_report"), {
            "title": "Power outage",
            "description": "No electricity in area",
            "location": "Karposh",
            "latitude": 41.9973,
            "longitude": 21.4280
        })

    assert response.status_code in [200, 302]
    assert mock_ollama.called


@pytest.mark.django_db
def test_submit_report_basic(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    with patch("apps.reports.services.generate_ai_summary") as mock_ai:
        mock_ai.return_value = "AI skipped"

        response = client.post(reverse("submit_report"), {
            "title": "Noise complaint",
            "description": "Loud noise at night",
            "location": "Chair",
            "latitude": 41.9973,
            "longitude": 21.4280
        })

    assert response.status_code in [200, 302]


def test_generate_ai_summary_success(monkeypatch):
    from apps.reports.services import generate_ai_summary

    monkeypatch.setattr(
        "apps.reports.services.call_ollama",
        lambda x: {"response": "OK AI"}
    )

    result = generate_ai_summary("test")
    assert result == "OK AI"