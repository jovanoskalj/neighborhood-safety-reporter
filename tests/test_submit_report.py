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
