"""Interactive map view tests (task T-14).

Covers the ``map_view`` page and the ``reports_json`` AJAX endpoint it drives.
"""
import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.reports.models import Report


def _make_report(user, **overrides):
    """Create a minimal Report row with sensible defaults."""
    defaults = {
        "citizen": user,
        "description": "Test report",
        "latitude": "41.996120",
        "longitude": "21.431442",
        "category": "safety",
        "priority": "normal",
        "status": "new",
        "sector": "safety",
        "municipality": "aerodrom",
    }
    defaults.update(overrides)
    return Report.objects.create(**defaults)


@pytest.fixture
def map_dataset(db, citizen_user):
    """Seed four reports covering each status/category/municipality group."""
    _make_report(citizen_user, status="new", category="safety", municipality="aerodrom")
    _make_report(citizen_user, status="in_progress", category="infrastructure", municipality="centar")
    _make_report(citizen_user, status="resolved", category="utilities", municipality="aerodrom")
    _make_report(citizen_user, status="unclassified", category="other", municipality="bitola")
    return citizen_user


# ---------------------------------------------------------------------------
# map_view page
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_map_view_redirects_guest_to_login(client):
    response = client.get(reverse("map_view"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_map_view_renders_filters_and_leaflet(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("map_view"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "reports-map" in content  # map container present
    assert "leaflet" in content.lower()  # Leaflet script tag
    assert 'id="filter-category"' in content
    assert 'id="filter-status"' in content
    assert 'id="filter-municipality"' in content


@pytest.mark.django_db
def test_map_view_municipality_dropdown_shows_macedonian_labels(client, citizen_user, map_dataset):
    """The dropdown must show human-readable labels, not the DB slug."""
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("map_view"))
    content = response.content.decode()

    # Slugs present as option values; Macedonian labels as the visible text
    assert 'value="aerodrom"' in content
    assert "Аеродром" in content
    assert 'value="bitola"' in content
    assert "Битола" in content


# ---------------------------------------------------------------------------
# reports_json endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_reports_json_requires_authentication(client):
    response = client.get(reverse("reports_json"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_reports_json_returns_all_reports_by_default(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json"))

    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert len(body["results"]) == 4


@pytest.mark.django_db
def test_reports_json_response_shape(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json"))
    first = response.json()["results"][0]

    expected_keys = {
        "id", "description", "status", "status_label",
        "category", "category_label", "municipality",
        "lat", "lng",
    }
    assert expected_keys <= set(first.keys())
    assert isinstance(first["lat"], float)
    assert isinstance(first["lng"], float)


@pytest.mark.django_db
def test_reports_json_filters_by_status(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json") + "?status=resolved")

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "resolved"


@pytest.mark.django_db
def test_reports_json_filters_by_category(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json") + "?category=infrastructure")

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["category"] == "infrastructure"


@pytest.mark.django_db
def test_reports_json_filters_by_municipality(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json") + "?municipality=aerodrom")

    results = response.json()["results"]
    assert len(results) == 2
    assert all(item["municipality"] == "aerodrom" for item in results)


@pytest.mark.django_db
def test_reports_json_combined_filters(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(
        reverse("reports_json") + "?municipality=aerodrom&status=new"
    )

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["municipality"] == "aerodrom"
    assert results[0]["status"] == "new"


@pytest.mark.django_db
def test_reports_json_empty_filter_returns_nothing(client, citizen_user, map_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("reports_json") + "?status=new&category=utilities")

    # New + utilities doesn't match any seeded row
    assert response.json()["results"] == []
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