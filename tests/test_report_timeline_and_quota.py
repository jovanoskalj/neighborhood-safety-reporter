import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.reports.models import Report, ReportStatusHistory


@pytest.mark.django_db
def test_report_creation_logs_initial_status_history(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    payload = {
        "description": "Water leak near building",
        "latitude": "41.998100",
        "longitude": "21.425400",
    }

    with patch("apps.reports.views.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "utilities",
            "priority": "normal",
            "sector": "utilities",
            "status": "new",
        }
        response = client.post(
            reverse("reports_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    assert response.status_code == 201
    report = Report.objects.get()
    history = ReportStatusHistory.objects.filter(report=report)
    assert history.count() == 1
    assert history.first().to_status == "new"


@pytest.mark.django_db
def test_status_update_creates_timeline_entry(client, officer_user, citizen_user):
    UserProfile.objects.update_or_create(
        user=officer_user,
        defaults={"role": "officer", "sector": "safety"},
    )

    report = Report.objects.create(
        citizen=citizen_user,
        description="Unsafe crossing",
        latitude=41.99,
        longitude=21.43,
        category="safety",
        priority="urgent",
        status="new",
        sector="safety",
        ai_processed=True,
    )
    ReportStatusHistory.objects.create(report=report, to_status="new")

    client.login(username="officer", password="officer123")
    response = client.post(
        reverse("update_report_status", kwargs={"report_id": report.id}),
        data={"status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert ReportStatusHistory.objects.filter(report=report, to_status="in_progress").exists()


@pytest.mark.django_db
def test_submit_page_shows_remaining_quota(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    for i in range(7):
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

    response = client.get(reverse("submit_report"))

    assert response.status_code == 200
    content = response.content.decode().lower()
    assert "преостанати пријави" in content
    assert "3 / 10" in content


@pytest.mark.django_db
def test_reports_api_includes_popup_detail_fields(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    report = Report.objects.create(
        citizen=citizen_user,
        description="Street light broken",
        latitude=41.998100,
        longitude=21.425400,
        category="infrastructure",
        priority="urgent",
        status="new",
        sector="infrastructure",
        ai_processed=True,
    )

    response = client.get(reverse("reports_api"))

    assert response.status_code == 200
    item = next(x for x in response.json()["results"] if x["id"] == report.id)
    assert item["status_display"]
    assert item["priority_display"]
    assert item["category_display"]
    assert item["detail_url"] == reverse("report_detail", args=[report.id])


@pytest.mark.django_db
@patch("apps.reports.views.send_report_created_email")
@patch("apps.reports.views.classify_report")
def test_report_creation_triggers_email(mock_classify, mock_send_created, client, citizen_user):
    mock_classify.return_value = {
        "category": "other",
        "priority": "normal",
        "sector": "admin",
        "status": "new",
    }
    client.login(username="citizen", password="citizen123")

    response = client.post(
        reverse("submit_report"),
        data={
            "description": "Sidewalk damage",
            "latitude": "41.998100",
            "longitude": "21.425400",
        },
    )

    assert response.status_code == 302
    assert mock_send_created.call_count == 1


@pytest.mark.django_db
@patch("apps.reports.views.send_report_status_changed_email")
def test_status_change_triggers_email(mock_send_status, client, officer_user, citizen_user):
    UserProfile.objects.update_or_create(
        user=officer_user,
        defaults={"role": "officer", "sector": "safety"},
    )

    report = Report.objects.create(
        citizen=citizen_user,
        description="Unsafe crossing",
        latitude=41.99,
        longitude=21.43,
        category="safety",
        priority="urgent",
        status="new",
        sector="safety",
        ai_processed=True,
    )

    client.login(username="officer", password="officer123")
    response = client.post(
        reverse("update_report_status", kwargs={"report_id": report.id}),
        data={"status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert mock_send_status.call_count == 1
