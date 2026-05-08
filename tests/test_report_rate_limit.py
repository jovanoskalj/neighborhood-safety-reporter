import json

import pytest
from django.urls import reverse

from apps.reports.models import Report


@pytest.mark.django_db
def test_create_report_rate_limit_returns_429(client, citizen_user):
    """The JSON `create_report` endpoint enforces the 10/24h cap."""
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
        reverse("create_report"),
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 429
    body = response.json()
    assert "limit" in body
    assert body["limit"] == 10


@pytest.mark.django_db
def test_submit_report_ui_rate_limit_returns_429(client, citizen_user):
    """The HTML `submit_report` form enforces the 10/24h cap and re-renders the form."""
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
