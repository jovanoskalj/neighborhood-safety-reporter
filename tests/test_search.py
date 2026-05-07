"""Search & filter API tests."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.reports.models import Report


@pytest.fixture
def search_dataset(db, citizen_user):
    """Seed reports spanning every filter dimension."""
    now = timezone.now()
    rows = [
        Report.objects.create(
            citizen=citizen_user, description="Road pothole near park",
            latitude="41.000000", longitude="21.000000",
            category="infrastructure", priority="urgent",
            status="new", sector="infrastructure",
        ),
        Report.objects.create(
            citizen=citizen_user, description="Streetlight not working",
            latitude="41.100000", longitude="21.100000",
            category="utilities", priority="normal",
            status="in_progress", sector="utilities",
        ),
        Report.objects.create(
            citizen=citizen_user, description="Vandalism report downtown",
            latitude="41.200000", longitude="21.200000",
            category="safety", priority="normal",
            status="resolved", sector="safety",
        ),
        Report.objects.create(
            citizen=citizen_user, description="Water pipe leak",
            latitude="42.500000", longitude="22.500000",
            category="utilities", priority="low",
            status="new", sector="utilities",
        ),
    ]
    # Push one row into the past so date-range tests have something to bite.
    Report.objects.filter(pk=rows[0].pk).update(created_at=now - timedelta(days=30))
    return rows


def _json_get(client, url):
    return client.get(url, HTTP_ACCEPT="application/json")


# ---------------------------------------------------------------------------
# Landing page vs filter branch
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_params_renders_public_landing_page(client):
    response = client.get(reverse("home"))
    assert response.status_code == 200
    # No reports table on the landing page.
    assert b"reports_page" not in response.content
    assert b"<table" not in response.content


@pytest.mark.django_db
def test_filter_branch_requires_authentication_json(client, search_dataset):
    response = _json_get(client, reverse("home") + "?category=safety")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


@pytest.mark.django_db
def test_filter_branch_requires_authentication_html_redirects(client, search_dataset):
    response = client.get(reverse("home") + "?category=safety")
    assert response.status_code == 302
    assert reverse("login") in response.url
    assert "next=" in response.url


# ---------------------------------------------------------------------------
# Individual filters
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_filter_by_category(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?category=utilities")

    body = response.json()
    assert body["count"] == 2
    assert all(r["category"] == "utilities" for r in body["results"])


@pytest.mark.django_db
def test_filter_by_status(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?status=resolved")

    assert response.json()["count"] == 1
    assert response.json()["results"][0]["status"] == "resolved"


@pytest.mark.django_db
def test_filter_by_sector(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?sector=safety")

    assert response.json()["count"] == 1


@pytest.mark.django_db
def test_filter_by_priority(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?priority=normal")

    assert response.json()["count"] == 2


@pytest.mark.django_db
def test_filter_by_keyword_matches_description(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?keyword=pipe")

    body = response.json()
    assert body["count"] == 1
    assert "pipe" in body["results"][0]["description"].lower()


@pytest.mark.django_db
def test_filter_by_date_range_from_only(client, citizen_user, search_dataset):
    """The 30-days-ago row must be excluded by ?from=today."""
    client.login(username="citizen", password="citizen123")
    today = timezone.now().date().isoformat()
    response = _json_get(client, reverse("home") + f"?from={today}")

    body = response.json()
    assert body["count"] == 3  # three of four rows are from "now"


@pytest.mark.django_db
def test_filter_by_date_range_to_only(client, citizen_user, search_dataset):
    """`?to=yesterday` must include only the backdated row."""
    client.login(username="citizen", password="citizen123")
    yesterday = (timezone.now() - timedelta(days=1)).date().isoformat()
    response = _json_get(client, reverse("home") + f"?to={yesterday}")

    assert response.json()["count"] == 1


@pytest.mark.django_db
def test_filter_by_bounding_box(client, citizen_user, search_dataset):
    """Only rows inside the lat/lng box should be returned."""
    client.login(username="citizen", password="citizen123")
    response = _json_get(
        client,
        reverse("home") + "?lat_min=41.0&lat_max=41.25&lng_min=21.0&lng_max=21.25",
    )

    body = response.json()
    assert body["count"] == 3  # three rows fall in that box; the 42.5 row is excluded


@pytest.mark.django_db
def test_combined_filters_are_anded(client, citizen_user, search_dataset):
    """Combining two filters must intersect their results."""
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?category=utilities&status=new")

    body = response.json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["category"] == "utilities"
    assert row["status"] == "new"


# ---------------------------------------------------------------------------
# Tolerance for malformed input
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_invalid_date_is_silently_ignored(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?from=not-a-date")

    assert response.status_code == 200
    assert response.json()["count"] == 4  # no rows filtered out


@pytest.mark.django_db
def test_invalid_latitude_is_silently_ignored(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = _json_get(client, reverse("home") + "?lat_min=abc")

    assert response.status_code == 200
    assert response.json()["count"] == 4


# ---------------------------------------------------------------------------
# Response shape & pagination
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_json_response_shape(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    body = _json_get(client, reverse("home") + "?category=utilities").json()

    assert set(body.keys()) == {"count", "num_pages", "page", "results"}
    assert isinstance(body["results"], list)
    first = body["results"][0]
    for key in ("id", "description", "latitude", "longitude",
                "category", "priority", "sector", "status",
                "ai_processed", "created_at"):
        assert key in first


@pytest.mark.django_db
def test_pagination_metadata(client, citizen_user, settings):
    client.login(username="citizen", password="citizen123")
    # 25 rows → 2 pages at 20 per page.
    for i in range(25):
        Report.objects.create(
            citizen=User.objects.get(username="citizen"),
            description=f"r{i}", latitude="41.0", longitude="21.0",
        )

    page1 = _json_get(client, reverse("home") + "?category=other").json()
    page2 = _json_get(client, reverse("home") + "?category=other&page=2").json()

    assert page1["count"] == 25
    assert page1["num_pages"] == 2
    assert page1["page"] == 1
    assert len(page1["results"]) == 20
    assert page2["page"] == 2
    assert len(page2["results"]) == 5


# ---------------------------------------------------------------------------
# Content negotiation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_format_query_param_triggers_json(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("home") + "?category=utilities&format=json")

    assert response["Content-Type"].startswith("application/json")
    assert response.json()["count"] == 2


@pytest.mark.django_db
def test_html_response_renders_results_table(client, citizen_user, search_dataset):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("home") + "?category=utilities")

    assert response.status_code == 200
    content = response.content.decode()
    assert "<table" in content
    # Both utilities rows should be present in the table body.
    assert "Streetlight not working" in content
    assert "Water pipe leak" in content
