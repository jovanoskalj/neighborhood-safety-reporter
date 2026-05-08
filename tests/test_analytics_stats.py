"""Tests for GET /analytics/stats/ endpoint."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.reports.models import Report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(user, **kwargs):
    """Create a minimal Report, allowing field overrides via kwargs."""
    defaults = {
        "citizen": user,
        "description": "Test report",
        "latitude": "41.996120",
        "longitude": "21.431442",
        "category": "safety",
        "priority": "normal",
        "status": "new",
        "sector": "safety",
    }
    defaults.update(kwargs)
    return Report.objects.create(**defaults)


@pytest.fixture
def staff_user(db):
    """An officer-level user used to access the stats endpoint."""
    from django.contrib.auth.models import Group
    group, _ = Group.objects.get_or_create(name="officer")
    user = User.objects.create_user(username="officer_stats", password="officer123")
    user.groups.add(group)
    return user


@pytest.fixture
def report_dataset(db, staff_user):
    """Seed several reports covering all grouping dimensions."""
    _make_report(staff_user, category="safety", priority="urgent", status="new")
    _make_report(staff_user, category="safety", priority="normal", status="in_progress")
    _make_report(staff_user, category="infrastructure", priority="low", status="resolved")
    _make_report(staff_user, category="health", priority="urgent", status="new")
    return staff_user


# ---------------------------------------------------------------------------
# Basic connectivity
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stats_endpoint_accessible(client, staff_user):
    client.force_login(staff_user)
    response = client.get(reverse("api_analytics:stats"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_stats_returns_json(client, staff_user):
    client.force_login(staff_user)
    response = client.get(reverse("api_analytics:stats"))
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_stats_post_not_allowed(client, staff_user):
    """Endpoint must only accept GET requests."""
    client.force_login(staff_user)
    response = client.post(reverse("api_analytics:stats"))
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stats_has_required_keys(client, staff_user, report_dataset):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats")).json()

    assert "total" in data
    assert "by_category" in data
    assert "by_status" in data
    assert "by_priority" in data
    assert "by_period" in data
    assert "period_type" in data["by_period"]
    assert "data" in data["by_period"]


@pytest.mark.django_db
def test_stats_total_count(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats")).json()
    assert data["total"] == 4


@pytest.mark.django_db
def test_stats_by_category_structure(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats")).json()

    labels = {item["label"] for item in data["by_category"]}
    assert "safety" in labels
    assert "infrastructure" in labels
    assert "health" in labels

    for item in data["by_category"]:
        assert "label" in item
        assert "count" in item


@pytest.mark.django_db
def test_stats_by_category_counts(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats")).json()

    counts = {item["label"]: item["count"] for item in data["by_category"]}
    assert counts["safety"] == 2
    assert counts["infrastructure"] == 1
    assert counts["health"] == 1


@pytest.mark.django_db
def test_stats_by_status_counts(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats")).json()

    counts = {item["label"]: item["count"] for item in data["by_status"]}
    assert counts["new"] == 2
    assert counts["in_progress"] == 1
    assert counts["resolved"] == 1


@pytest.mark.django_db
def test_stats_by_priority_counts(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats")).json()

    counts = {item["label"]: item["count"] for item in data["by_priority"]}
    assert counts["urgent"] == 2
    assert counts["normal"] == 1
    assert counts["low"] == 1


@pytest.mark.django_db
def test_stats_filters_by_municipality(client, staff_user):
    client.force_login(staff_user)
    _make_report(staff_user, municipality="centar", category="safety")
    _make_report(staff_user, municipality="karposh", category="health")

    data = client.get(reverse("api_analytics:stats") + "?municipality=centar").json()

    assert data["total"] == 1
    assert data["by_category"] == [{"label": "safety", "count": 1}]


# ---------------------------------------------------------------------------
# Period parameter
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stats_default_period_is_monthly(client, staff_user):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats")).json()
    assert data["by_period"]["period_type"] == "monthly"


@pytest.mark.django_db
def test_stats_period_weekly(client, staff_user, report_dataset):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats") + "?period=weekly").json()
    assert data["by_period"]["period_type"] == "weekly"
    assert isinstance(data["by_period"]["data"], list)


@pytest.mark.django_db
def test_stats_period_monthly(client, staff_user, report_dataset):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats") + "?period=monthly").json()
    assert data["by_period"]["period_type"] == "monthly"


@pytest.mark.django_db
def test_stats_period_yearly(client, staff_user, report_dataset):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats") + "?period=yearly").json()
    assert data["by_period"]["period_type"] == "yearly"


@pytest.mark.django_db
def test_stats_invalid_period_falls_back_to_monthly(client, staff_user):
    """Invalid period values must not crash and must default to monthly."""
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats") + "?period=invalid_value").json()
    assert data["by_period"]["period_type"] == "monthly"


@pytest.mark.django_db
def test_stats_empty_period_falls_back_to_monthly(client, staff_user):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats") + "?period=").json()
    assert data["by_period"]["period_type"] == "monthly"


# ---------------------------------------------------------------------------
# Empty database edge case
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stats_empty_database(client, staff_user):
    client.force_login(staff_user)
    data = client.get(reverse("api_analytics:stats")).json()
    assert data["total"] == 0
    assert data["by_category"] == []
    assert data["by_status"] == []
    assert data["by_priority"] == []
    assert data["by_period"]["data"] == []


# ---------------------------------------------------------------------------
# Time-series data shape
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stats_time_series_items_have_period_and_count(client, report_dataset):
    client.force_login(report_dataset)
    data = client.get(reverse("api_analytics:stats") + "?period=monthly").json()

    for item in data["by_period"]["data"]:
        assert "period" in item
        assert "count" in item
        assert isinstance(item["count"], int)
