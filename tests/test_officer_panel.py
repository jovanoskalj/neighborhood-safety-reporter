"""Officer work panel tests."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.accounts.models import UserNotification
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


@pytest.mark.django_db
def test_officer_panel_includes_sector_map_controls(client, safety_officer, sector_reports):
    client.login(username="safety_officer", password="password123")
    content = client.get(reverse("officer_panel")).content.decode()

    assert 'id="sector-map"' in content
    assert 'id="heatmap-toggle"' in content
    assert 'id="map-filter-status"' in content
    assert 'id="map-filter-priority"' in content
    assert 'id="map-filter-municipality"' in content
    assert 'id="map-filter-category"' not in content
    assert 'Категорија:</span>' in content
    assert 'Општина:</span>' in content


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


@pytest.mark.django_db
def test_officer_sector_isolation(client, safety_officer, sector_reports):
    """Officer panel surfaces own-sector rows and hides other-sector rows."""
    client.login(username="safety_officer", password="password123")
    response = client.get(reverse("officer_panel"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Urgent safety issue" in content
    assert "Normal safety issue" in content
    assert "Utilities issue" not in content


@pytest.mark.django_db
@patch("apps.notifications.senders.send_mail")
def test_status_update_sends_email(mock_send_mail, client, safety_officer, sector_reports):
    """Status change triggers an email to the report's citizen (FR-14)."""
    client.login(username="safety_officer", password="password123")
    report = sector_reports[0]  # sector=safety
    assert report.citizen.email, "citizen fixture must have an email"

    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps({"status": "resolved"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    mock_send_mail.assert_called_once()
    recipient_list = mock_send_mail.call_args.kwargs["recipient_list"]
    assert report.citizen.email in recipient_list


@pytest.mark.django_db
@patch("apps.notifications.senders.send_mail")
def test_status_update_creates_in_app_notification(mock_send_mail, client, safety_officer, sector_reports):
    client.login(username="safety_officer", password="password123")
    report = sector_reports[0]

    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps({"status": "in_progress"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    notification = UserNotification.objects.get(
        user=report.citizen,
        report=report,
        type="status_change",
    )
    assert "Статусот" in notification.title
    assert "Во тек" in notification.message


@pytest.mark.django_db
def test_officer_can_reassign_wrong_sector_report(client, safety_officer, sector_reports):
    utilities_group, _ = Group.objects.get_or_create(name="officer")
    destination_worker = User.objects.create_user(
        username="utilities_worker",
        email="utilities@test.com",
        password="password123",
    )
    destination_worker.groups.add(utilities_group)
    destination_worker.profile.role = "officer"
    destination_worker.profile.sector = "utilities"
    destination_worker.profile.municipality = ""
    destination_worker.profile.save()

    report = sector_reports[0]
    client.login(username="safety_officer", password="password123")
    response = client.post(
        reverse("reassign_report_sector", args=[report.pk]),
        {"sector": "utilities"},
    )

    assert response.status_code == 200
    report.refresh_from_db()
    assert report.sector == "utilities"
    assert report.assigned_officer is None
    assert not Report.objects.filter(pk=report.pk, sector="safety").exists()
    assert Report.objects.filter(pk=report.pk, sector="utilities").exists()
    assert UserNotification.objects.filter(
        user=destination_worker,
        report=report,
        type="report_assigned",
        title__icontains="пренасочена",
    ).exists()

    client.logout()
    client.login(username="utilities_worker", password="password123")
    destination_response = client.get(reverse("officer_panel"))
    assert report in list(destination_response.context["reports"])
