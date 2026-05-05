import pytest
from django.contrib.auth.models import User, Group
from django.urls import reverse

from apps.reports.models import Report
from apps.accounts.models import UserProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_LAT = 41.9981
BASE_LNG = 21.4254
CLUSTER_COUNT = 15


def make_citizen(username="cluster_citizen"):
    user = User.objects.create_user(username=username, password="test123", is_active=True)
    group, _ = Group.objects.get_or_create(name="citizen")
    user.groups.add(group)
    UserProfile.objects.filter(user=user).update(role="citizen")
    return user


def seed_cluster(user, count=CLUSTER_COUNT):
    reports = []
    for i in range(count):
        reports.append(Report(
            citizen=user,
            description=f"Cluster report {i}",
            latitude=BASE_LAT + i * 0.00005,
            longitude=BASE_LNG + i * 0.00005,
            category="safety",
            priority="normal",
            status="new",
            sector="safety",
        ))
    Report.objects.bulk_create(reports)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cluster_user(db):
    return make_citizen("cluster_citizen")


@pytest.fixture
def cluster_dataset(cluster_user):
    seed_cluster(cluster_user)
    return cluster_user


# ---------------------------------------------------------------------------
# T-42 Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cluster_seed_creates_correct_count(cluster_dataset):
    assert Report.objects.filter(citizen=cluster_dataset).count() == CLUSTER_COUNT


@pytest.mark.django_db
def test_map_cluster_renders(client, cluster_dataset):
    client.login(username="cluster_citizen", password="test123")
    response = client.get(reverse("reports_json"))

    assert response.status_code == 200
    data = response.json()
    results = data.get("results", [])

    assert len(results) >= CLUSTER_COUNT, (
        f"Expected at least {CLUSTER_COUNT} reports returned for client-side "
        f"clustering, got {len(results)}."
    )


@pytest.mark.django_db
def test_all_seeded_reports_appear_in_response(client, cluster_dataset):
    client.login(username="cluster_citizen", password="test123")
    response = client.get(reverse("reports_json"))

    assert response.status_code == 200
    results = response.json().get("results", [])

    assert len(results) == CLUSTER_COUNT, (
        f"Expected {CLUSTER_COUNT} reports in response, got {len(results)}. "
        "All pins must be returned so the client can cluster them."
    )


@pytest.mark.django_db
def test_cluster_reports_have_lat_lng(client, cluster_dataset):
    client.login(username="cluster_citizen", password="test123")
    response = client.get(reverse("reports_json"))

    results = response.json().get("results", [])
    for r in results:
        assert "lat" in r and "lng" in r, (
            f"Report {r.get('id')} is missing lat/lng coordinates."
        )
        assert r["lat"] is not None and r["lng"] is not None


@pytest.mark.django_db
def test_isolated_pin_not_clustered(client, db):
    user = make_citizen("isolated_citizen")
    Report.objects.create(
        citizen=user,
        description="Isolated pin",
        latitude=42.5,
        longitude=22.5,
        category="safety",
        priority="normal",
        status="new",
        sector="safety",
    )

    client.login(username="isolated_citizen", password="test123")
    response = client.get(reverse("reports_json"))

    assert response.status_code == 200
    results = response.json().get("results", [])

    assert len(results) == 1, (
        f"Expected exactly 1 result for an isolated pin, got {len(results)}."
    )
    pin = results[0]
    assert not pin.get("cluster", False), (
        "A single isolated pin should not be marked as a cluster."
    )


@pytest.mark.django_db
def test_cluster_pins_coords_are_within_expected_bbox(client, cluster_dataset):
    client.login(username="cluster_citizen", password="test123")
    response = client.get(reverse("reports_json"))

    results = response.json().get("results", [])
    lat_range = (BASE_LAT - 0.01, BASE_LAT + 0.01)
    lng_range = (BASE_LNG - 0.01, BASE_LNG + 0.01)

    for r in results:
        assert lat_range[0] <= r["lat"] <= lat_range[1], (
            f"Report lat {r['lat']} is outside expected cluster bbox."
        )
        assert lng_range[0] <= r["lng"] <= lng_range[1], (
            f"Report lng {r['lng']} is outside expected cluster bbox."
        )
