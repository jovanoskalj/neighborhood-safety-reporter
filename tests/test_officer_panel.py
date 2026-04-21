"""Officer work panel tests (task T-15).

Covers sector-scoped access, the priority/status filters on the list view,
and the PATCH endpoint that persists status + internal notes.
"""
import json

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.reports.models import Report


@pytest.fixture
def safety_officer(db):
    """Officer whose profile.sector == 'safety'."""
    group, _ = Group.objects.get_or_create(name="officer")
    user = User.objects.create_user(
        username="safety_officer",
        email="safety@test.com",
        password="password123",
    )
    user.groups.add(group)
    # Profile is auto-created by the post_save signal; update its fields.
    profile = user.profile
    profile.role = "officer"
    profile.sector = "safety"
    profile.save()
    return user


@pytest.fixture
def sector_reports(db, citizen_user):
    """Seed reports across sectors, statuses, and priorities."""
    r1 = Report.objects.create(
        citizen=citizen_user, description="Urgent safety issue",
        latitude="41.000000", longitude="21.000000",
        category="safety", priority="urgent",
        status="new", sector="safety",
    )
    r2 = Report.objects.create(
        citizen=citizen_user, description="Normal safety issue",
        latitude="41.100000", longitude="21.100000",
        category="safety", priority="normal",
        status="new", sector="safety",
    )
    r3 = Report.objects.create(
        citizen=citizen_user, description="Utilities issue",
        latitude="41.200000", longitude="21.200000",
        category="utilities", priority="low",
        status="in_progress", sector="utilities",
    )
    return [r1, r2, r3]


# ---------------------------------------------------------------------------
# officer_panel access control
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_officer_panel_redirects_non_officer(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("officer_panel"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_officer_panel_lists_only_own_sector(client, safety_officer, sector_reports):
    client.login(username="safety_officer", password="password123")
    response = client.get(reverse("officer_panel"))

    assert response.status_code == 200
    sectors = list(response.context["reports"].values_list("sector", flat=True))
    assert sectors == ["safety", "safety"]


# ---------------------------------------------------------------------------
# Filter alignment (the spec-bug fix)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_priority_filter_uses_model_choices(client, safety_officer, sector_reports):
    """``?priority=urgent`` must match model's ``PRIORITY_CHOICES`` exactly."""
    client.login(username="safety_officer", password="password123")
    response = client.get(reverse("officer_panel") + "?priority=urgent")

    reports = list(response.context["reports"])
    assert len(reports) == 1
    assert reports[0].priority == "urgent"


@pytest.mark.django_db
def test_priority_filter_dropdown_exposes_model_values(client, safety_officer):
    """The HTML dropdown must offer the same slugs the backend filter accepts."""
    client.login(username="safety_officer", password="password123")
    content = client.get(reverse("officer_panel")).content.decode()

    assert 'value="urgent"' in content
    assert 'value="normal"' in content
    assert 'value="low"' in content
    # Stale options that don't exist in the model must not be present.
    assert 'value="medium"' not in content
    assert 'value="high"' not in content
    assert 'value="critical"' not in content


# ---------------------------------------------------------------------------
# PATCH endpoint: internal_note persistence
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_patch_persists_status_and_internal_note(client, safety_officer, sector_reports):
    client.login(username="safety_officer", password="password123")
    report = sector_reports[0]  # sector=safety

    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps({"status": "in_progress", "internal_note": "Investigating"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["internal_note"] == "Investigating"

    report.refresh_from_db()
    assert report.status == "in_progress"
    assert report.internal_note == "Investigating"
    assert report.assigned_officer == safety_officer


@pytest.mark.django_db
def test_patch_preserves_existing_note_when_not_provided(client, safety_officer, sector_reports):
    """Omitting ``internal_note`` from the payload must leave the field untouched."""
    client.login(username="safety_officer", password="password123")
    report = sector_reports[0]
    report.internal_note = "Pre-existing officer note"
    report.save(update_fields=["internal_note"])

    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps({"status": "resolved"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    report.refresh_from_db()
    assert report.status == "resolved"
    assert report.internal_note == "Pre-existing officer note"


@pytest.mark.django_db
def test_patch_cross_sector_is_forbidden(client, safety_officer, sector_reports):
    """Safety officer must not be able to touch a utilities-sector report."""
    client.login(username="safety_officer", password="password123")
    other_sector_report = sector_reports[2]  # sector=utilities

    response = client.patch(
        reverse("update_report_status", args=[other_sector_report.pk]),
        data=json.dumps({"status": "resolved", "internal_note": "mine now"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    other_sector_report.refresh_from_db()
    assert other_sector_report.status == "in_progress"
    assert other_sector_report.internal_note == ""


@pytest.mark.django_db
def test_patch_rejected_for_non_officer(client, citizen_user, sector_reports):
    client.login(username="citizen", password="citizen123")
    report = sector_reports[0]

    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps({"status": "resolved"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    report.refresh_from_db()
    assert report.status == "new"
