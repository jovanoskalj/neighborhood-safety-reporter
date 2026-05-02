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


@pytest.mark.django_db
def test_map_endpoint_returns_coords(client):
    user = User.objects.create_user(username="map_citizen", password="123")

    Report.objects.create(
        citizen=user,
        description="Test",
        latitude="41.998100",
        longitude="21.425400",
        category="safety",
        status="new",
        sector="safety",
    )

    client.login(username="map_citizen", password="123")
    response = client.get(reverse("reports_json"))

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    report = data["results"][0]
    assert report["lat"] == 41.9981
    assert report["lng"] == 21.4254


