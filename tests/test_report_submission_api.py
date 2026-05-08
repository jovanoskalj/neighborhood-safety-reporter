import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.reports.models import Report


@pytest.mark.django_db
def test_submit_report_with_ai(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    payload = {
        "description": "Broken street light near school entrance",
        "latitude": "41.998100",
        "longitude": "21.425400",
    }

    with patch("apps.reports.views.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "infrastructure",
            "priority": "urgent",
            "sector": "infrastructure",
            "status": "new",
        }
        response = client.post(
            reverse("reports_api"),
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
def test_submit_report_ai_failure(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    payload = {
        "description": "Unclear issue",
        "latitude": "41.990000",
        "longitude": "21.430000",
    }

    with patch("apps.reports.views.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "other",
            "priority": "normal",
            "sector": "admin",
            "status": "unclassified",
        }
        response = client.post(
            reverse("reports_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    assert response.status_code == 201
    report = Report.objects.get()
    assert report.status == "unclassified"
    assert report.category == "other"
