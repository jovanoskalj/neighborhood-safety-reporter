import pytest
from django.urls import reverse

from apps.reports.models import Report


@pytest.mark.django_db
def test_submit_report_flags_duplicate_within_radius_and_similar_text(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    existing = Report.objects.create(
        citizen=citizen_user,
        description="Голема дупка пред училиштето.",
        category="infrastructure",
        priority="urgent",
        municipality="aerodrom",
        latitude="41.998100",
        longitude="21.425400",
        status="new",
    )

    payload = {
        "description": "Има голема дупка пред училиштето!",
        "category": "infrastructure",
        "priority": "urgent",
        "municipality": "aerodrom",
        # ~14m away in latitude direction
        "latitude": "41.998230",
        "longitude": "21.425400",
    }

    response = client.post(reverse("submit_report"), data=payload)
    assert response.status_code == 302

    created = Report.objects.exclude(pk=existing.pk).get()
    assert created.is_duplicate is True
    assert created.duplicate_of_id == existing.pk
    assert created.duplicate_verdict == "pending"


@pytest.mark.django_db
def test_submit_report_not_duplicate_when_far_away(client, citizen_user):
    client.login(username="citizen", password="citizen123")

    Report.objects.create(
        citizen=citizen_user,
        description="Голема дупка пред училиштето.",
        category="infrastructure",
        priority="urgent",
        municipality="aerodrom",
        latitude="41.998100",
        longitude="21.425400",
        status="new",
    )

    payload = {
        "description": "Голема дупка пред училиштето.",
        "category": "infrastructure",
        "priority": "urgent",
        "municipality": "aerodrom",
        # ~3.3km away in latitude direction
        "latitude": "42.028100",
        "longitude": "21.425400",
    }

    response = client.post(reverse("submit_report"), data=payload)
    assert response.status_code == 302

    created = Report.objects.order_by("-id").first()
    assert created.is_duplicate is False
    assert created.duplicate_of_id is None
    assert created.duplicate_verdict == "none"


@pytest.mark.django_db
def test_submit_report_still_detects_duplicates_older_than_30_days(client, citizen_user):
    """Regression: do not silently miss duplicates due to small lookback window."""
    from datetime import timedelta

    from django.utils import timezone

    client.login(username="citizen", password="citizen123")

    existing = Report.objects.create(
        citizen=citizen_user,
        description="Голема дупка пред училиштето.",
        category="infrastructure",
        priority="urgent",
        municipality="aerodrom",
        latitude="41.998100",
        longitude="21.425400",
        status="new",
    )
    Report.objects.filter(pk=existing.pk).update(created_at=timezone.now() - timedelta(days=60))

    payload = {
        "description": "Има голема дупка пред училиштето!",
        "category": "infrastructure",
        "priority": "urgent",
        "municipality": "aerodrom",
        "latitude": "41.998230",
        "longitude": "21.425400",
    }

    response = client.post(reverse("submit_report"), data=payload)
    assert response.status_code == 302

    created = Report.objects.exclude(pk=existing.pk).get()
    assert created.is_duplicate is True
    assert created.duplicate_of_id == existing.pk
    assert created.duplicate_verdict == "pending"


@pytest.mark.django_db
def test_admin_confirm_duplicate(client, admin_user, citizen_user):
    client.login(username="admin", password="admin123")
    original = Report.objects.create(
        citizen=citizen_user,
        description="Original.",
        category="infrastructure",
        priority="normal",
        municipality="aerodrom",
        latitude="41.998100",
        longitude="21.425400",
        status="new",
    )
    newer = Report.objects.create(
        citizen=citizen_user,
        description="Newer.",
        category="infrastructure",
        priority="normal",
        municipality="aerodrom",
        latitude="41.998200",
        longitude="21.425400",
        status="new",
        is_duplicate=True,
        duplicate_of=original,
        duplicate_verdict="pending",
    )
    response = client.post(reverse("review_duplicate_report", args=[newer.id]), {"action": "confirm"})
    assert response.status_code == 302
    newer.refresh_from_db()
    assert newer.duplicate_verdict == "confirmed"
    assert newer.is_duplicate is True
    assert newer.duplicate_of_id == original.pk


@pytest.mark.django_db
def test_admin_reject_duplicate(client, admin_user, citizen_user):
    client.login(username="admin", password="admin123")
    original = Report.objects.create(
        citizen=citizen_user,
        description="Original.",
        category="infrastructure",
        priority="normal",
        municipality="aerodrom",
        latitude="41.998100",
        longitude="21.425400",
        status="new",
    )
    newer = Report.objects.create(
        citizen=citizen_user,
        description="Newer.",
        category="infrastructure",
        priority="normal",
        municipality="aerodrom",
        latitude="41.998200",
        longitude="21.425400",
        status="new",
        is_duplicate=True,
        duplicate_of=original,
        duplicate_verdict="pending",
    )
    response = client.post(reverse("review_duplicate_report", args=[newer.id]), {"action": "reject"})
    assert response.status_code == 302
    newer.refresh_from_db()
    assert newer.duplicate_verdict == "rejected"
    assert newer.is_duplicate is False
    assert newer.duplicate_of_id is None

