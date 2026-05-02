import json

import pytest
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.reports.models import Report


@pytest.mark.django_db
def test_officer_sector_isolation(client, officer_user, citizen_user):
    UserProfile.objects.update_or_create(
        user=officer_user,
        defaults={"role": "officer", "sector": "health"},
    )

    visible_report = Report.objects.create(
        citizen=citizen_user,
        description="Hospital entrance blocked",
        latitude=41.99,
        longitude=21.43,
        category="health",
        priority="normal",
        status="new",
        sector="health",
        ai_processed=True,
    )
    hidden_report = Report.objects.create(
        citizen=citizen_user,
        description="Street light broken",
        latitude=41.98,
        longitude=21.41,
        category="infrastructure",
        priority="normal",
        status="new",
        sector="infrastructure",
        ai_processed=True,
    )

    client.login(username="officer", password="officer123")
    response = client.get(reverse("reports_api"))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert visible_report.id in ids
    assert hidden_report.id not in ids


@pytest.mark.django_db
def test_map_endpoint_returns_coords(client, citizen_user):
    Report.objects.create(
        citizen=citizen_user,
        description="Road hole",
        latitude=41.998100,
        longitude=21.425400,
        category="infrastructure",
        priority="normal",
        status="new",
        sector="infrastructure",
        ai_processed=True,
    )
    Report.objects.create(
        citizen=citizen_user,
        description="Road hole again",
        latitude=41.998110,
        longitude=21.425410,
        category="infrastructure",
        priority="normal",
        status="new",
        sector="infrastructure",
        ai_processed=True,
    )

    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_heatmap"))

    assert response.status_code == 200
    points = response.json()
    assert isinstance(points, list)
    assert {"lat", "lng", "weight"}.issubset(points[0].keys())
    assert sum(point["weight"] for point in points) >= 2


@pytest.mark.django_db
def test_officer_status_update_rejects_other_sector(client, officer_user, citizen_user):
    UserProfile.objects.update_or_create(
        user=officer_user,
        defaults={"role": "officer", "sector": "utilities"},
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
    response = client.patch(
        reverse("update_report_status", kwargs={"report_id": report.id}),
        data=json.dumps({"status": "in_progress"}),
        content_type="application/json",
    )

    assert response.status_code == 403
