import json
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from apps.accounts.models import UserProfile

from apps.reports.models import Report


@pytest.mark.django_db
def test_map_endpoint_returns_coords(client):
    user = User.objects.create_user(username="citizen", password="123")

    Report.objects.create(
        citizen=user,
        description="Test",
        latitude=41.9981,
        longitude=21.4254,
        category="safety",
        status="new",
        sector="safety"
    )

    client.login(username="citizen", password="123")

    response = client.get(reverse("reports_json"))

    assert response.status_code == 200

    data = response.json()

    assert "results" in data
    assert len(data["results"]) == 1

    report = data["results"][0]

    assert report["lat"] == 41.9981
    assert report["lng"] == 21.4254


@pytest.mark.django_db
def test_officer_sector_isolation(client):
    group, _ = Group.objects.get_or_create(name="officer")

    officer = User.objects.create_user(username="officer", password="123")
    officer.groups.add(group)

    profile, _ = UserProfile.objects.get_or_create(user=officer)
    profile.role = "officer"
    profile.sector = "safety"
    profile.phone = ""
    profile.save()

    citizen = User.objects.create_user(username="citizen", password="123")

    Report.objects.create(
        citizen=citizen,
        description="Visible report",
        sector="safety",
        latitude=41.9981,
        longitude=21.4254
    )

    Report.objects.create(
        citizen=citizen,
        description="Hidden report",
        sector="health",
        latitude=41.9981,
        longitude=21.4254
    )

    client.force_login(officer)

    response = client.get(reverse("officer_panel"))

    assert response.status_code == 200

    content = response.content.decode()

    assert "Visible report" in content
    assert "Hidden report" not in content


@pytest.mark.django_db
@patch("apps.accounts.views.send_mail")
def test_register_sends_email(mock_send_mail, client, settings):
    settings.SENDGRID_ENABLED = True

    response = client.post(reverse("register"), {
        "username": "testuser",
        "password1": "StrongPass123",
        "password2": "StrongPass123",
        "email": "test@test.com"
    })

    assert response.status_code == 302
    assert mock_send_mail.called


@pytest.mark.django_db
def test_status_update_success(client):
    group, _ = Group.objects.get_or_create(name="officer")

    officer = User.objects.create_user(username="officer", password="123")
    officer.groups.add(group)
    officer.save()

    profile, _ = UserProfile.objects.get_or_create(user=officer)
    profile.role = "officer"
    profile.sector = "safety"
    profile.phone = ""
    profile.save()

    citizen = User.objects.create_user(username="citizen", password="123")

    report = Report.objects.create(
        citizen=citizen,
        description="Test",
        sector="safety",
        status="new",
        latitude=41.9981,
        longitude=21.4254
    )

    client.force_login(officer)

    response = client.patch(
        reverse("update_report_status", args=[report.id]),
        data=json.dumps({"status": "resolved"}),
        content_type="application/json"
    )

    assert response.status_code == 200

    report.refresh_from_db()
    assert report.status == "resolved"
    assert report.assigned_officer == officer


@pytest.mark.django_db
def test_officer_cannot_update_other_sector(client):
    group, _ = Group.objects.get_or_create(name="officer")

    officer = User.objects.create_user(username="officer", password="123")
    officer.groups.add(group)

    profile, _ = UserProfile.objects.get_or_create(user=officer)
    profile.sector = "safety"
    profile.save()

    citizen = User.objects.create_user(username="citizen", password="123")

    report = Report.objects.create(
        citizen=citizen,
        description="Test",
        sector="health",
        status="new",
        latitude=41.9981,
        longitude=21.4254
    )

    client.login(username="officer", password="123")

    response = client.patch(
        f"/reports/{report.id}/status/",
        data=json.dumps({"status": "resolved"}),
        content_type="application/json"
    )

    assert response.status_code == 403