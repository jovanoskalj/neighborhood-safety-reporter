"""Submission-path tests named per the T-13 acceptance criteria."""
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.reports.models import Report


VALID_PAYLOAD = {
    "description": "Улично светло не работи на плоштад",
    "category": "utilities",
    "priority": "normal",
    "municipality": "aerodrom",
    "latitude": "41.997300",
    "longitude": "21.428000",
}


@pytest.mark.django_db
def test_submit_report_with_ai(client, citizen_user, settings):
    """Submitting the form creates a report and applies AI classification."""
    settings.AI_CLASSIFICATION_ENABLED = True
    client.login(username="citizen", password="citizen123")

    with patch("apps.reports.signals.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "safety",
            "priority": "urgent",
            "sector": "safety",
        }
        response = client.post(reverse("submit_report"), data=VALID_PAYLOAD)

    assert response.status_code == 302
    assert mock_classify.called
    assert Report.objects.count() == 1

    report = Report.objects.get()
    assert report.citizen == citizen_user
    assert report.status == "new"
    assert report.ai_processed is True
    # AI classifier output overrides the user's form selection (per T-12 spec).
    assert report.category == "safety"
    assert report.priority == "urgent"
    assert report.sector == "safety"


@pytest.mark.django_db
def test_submit_report_ai_failure(client, citizen_user, settings):
    """AI timeout: the report persists but is flagged ``unclassified`` (FR-09)."""
    settings.AI_CLASSIFICATION_ENABLED = True
    client.login(username="citizen", password="citizen123")

    with patch("apps.reports.signals.classify_report") as mock_classify:
        mock_classify.side_effect = TimeoutError("Ollama timeout")
        response = client.post(reverse("submit_report"), data=VALID_PAYLOAD)

    assert response.status_code == 302
    assert mock_classify.called
    assert Report.objects.count() == 1

    report = Report.objects.get()
    assert report.citizen == citizen_user
    assert report.status == "unclassified"
    assert report.ai_processed is False
import pytest
from unittest.mock import patch
from django.urls import reverse
from apps.reports.services import generate_ai_summary
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
    monkeypatch.setattr(
        "apps.reports.services.call_ollama",
        lambda x: {"response": "OK AI"}
    )

    result = generate_ai_summary("test")
    assert result == "OK AI"