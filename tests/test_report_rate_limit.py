import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.reports.models import Report


@pytest.mark.django_db
def test_reports_api_rate_limit_returns_429(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    for i in range(10):
        Report.objects.create(
            citizen=citizen_user,
            description=f"Existing report {i}",
            latitude=41.998100,
            longitude=21.425400,
            category="other",
            priority="normal",
            status="new",
            sector="admin",
            ai_processed=True,
        )

    payload = {
        "description": "New blocked report",
        "latitude": "41.998100",
        "longitude": "21.425400",
    }

    response = client.post(
        reverse("reports_api"),
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 429
    body = response.json()
    assert "limit" in body
    assert body["limit"] == 10


@pytest.mark.django_db
@patch("apps.reports.views.classify_report")
def test_submit_report_ui_rate_limit_returns_429(mock_classify, client, citizen_user):
    mock_classify.return_value = {
        "category": "other",
        "priority": "normal",
        "sector": "admin",
        "status": "new",
    }

    client.login(username="citizen", password="citizen123")

    for i in range(10):
        Report.objects.create(
            citizen=citizen_user,
            description=f"Existing report {i}",
            latitude=41.998100,
            longitude=21.425400,
            category="other",
            priority="normal",
            status="new",
            sector="admin",
            ai_processed=True,
        )

    response = client.post(
        reverse("submit_report"),
        data={
            "description": "Attempt over limit",
            "latitude": "41.998100",
            "longitude": "21.425400",
        },
    )

    assert response.status_code == 429
    assert "дневниот лимит" in response.content.decode().lower()
