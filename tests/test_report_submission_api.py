"""JSON `create_report` endpoint smoke tests.

Form-encoded variants live in `tests/test_create_report.py` (Django TestCase
style); these cover the JSON content-type path with pytest fixtures.
"""
import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.reports.models import Report


@pytest.mark.django_db
def test_create_report_with_ai(client, citizen_user, settings):
    """JSON POST runs the classification signal and returns the classified report."""
    settings.AI_CLASSIFICATION_ENABLED = True
    client.login(username="citizen", password="citizen123")

    payload = {
        "description": "Broken street light near school entrance",
        "latitude": "41.998100",
        "longitude": "21.425400",
    }

    with patch("apps.reports.signals.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "infrastructure",
            "priority": "urgent",
            "sector": "infrastructure",
        }
        response = client.post(
            reverse("create_report"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "infrastructure"
    assert body["priority"] == "urgent"
    assert body["sector"] == "infrastructure"
    assert body["status"] == "new"
    assert Report.objects.count() == 1


@pytest.mark.django_db
def test_create_report_ai_failure(client, citizen_user, settings):
    """When the classifier raises, the report still saves but is marked unclassified."""
    settings.AI_CLASSIFICATION_ENABLED = True
    client.login(username="citizen", password="citizen123")

    payload = {
        "description": "Unclear issue",
        "latitude": "41.990000",
        "longitude": "21.430000",
    }

    with patch("apps.reports.signals.classify_report") as mock_classify:
        mock_classify.side_effect = TimeoutError("classifier timeout")
        response = client.post(
            reverse("create_report"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    assert response.status_code == 201
    report = Report.objects.get()
    assert report.status == "unclassified"
    assert report.ai_processed is False
