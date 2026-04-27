"""Tests for the notifications log page and sender pipeline (task T-22)."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail  # noqa: F401  (patch target)
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.senders import send_status_change_email
from apps.reports.models import Report


@pytest.fixture
def admin_user(db):
    group, _ = Group.objects.get_or_create(name="admin")
    user = User.objects.create_user(
        username="admin_notify",
        email="admin_notify@test.com",
        password="AdminStrongPass9!",
    )
    user.groups.add(group)
    return user


@pytest.fixture
def report_with_citizen(db, citizen_user):
    return Report.objects.create(
        citizen=citizen_user,
        description="Test report",
        latitude=Decimal("41.998100"),
        longitude=Decimal("21.425400"),
        category="safety",
        priority="normal",
        sector="safety",
        status="new",
    )


# ---------------------------------------------------------------------------
# Sender records the attempt
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sender_records_notification_on_success(report_with_citizen):
    with patch("apps.notifications.senders.send_mail") as mock_send:
        notification = send_status_change_email(report_with_citizen)

    assert mock_send.called
    assert notification is not None
    assert notification.status == "sent"
    assert notification.type == "status_change"
    assert notification.recipient == report_with_citizen.citizen.email
    assert Notification.objects.filter(pk=notification.pk, status="sent").exists()


@pytest.mark.django_db
def test_sender_records_notification_on_failure(report_with_citizen):
    with patch("apps.notifications.senders.send_mail", side_effect=RuntimeError("SMTP down")):
        notification = send_status_change_email(report_with_citizen)

    assert notification is not None
    assert notification.status == "failed"
    assert Notification.objects.filter(pk=notification.pk, status="failed").exists()


@pytest.mark.django_db
def test_sender_skips_when_citizen_has_no_email(db):
    """A citizen without an email triggers no Notification row."""
    no_email_user = User.objects.create_user(username="no_email", password="x")
    assert no_email_user.email == ""
    report = Report.objects.create(
        citizen=no_email_user,
        description="x",
        latitude=Decimal("41.0"),
        longitude=Decimal("21.0"),
    )

    result = send_status_change_email(report)

    assert result is None
    assert Notification.objects.count() == 0


# ---------------------------------------------------------------------------
# Notifications log page (admin-only)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_notifications_log_admin_only_rejects_citizen(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("notifications_log"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_notifications_log_renders_rows_for_admin(client, admin_user):
    Notification.objects.create(
        type="status_change", subject="S", message="M",
        recipient="a@b.com", status="sent",
    )
    Notification.objects.create(
        type="status_change", subject="S", message="M",
        recipient="c@d.com", status="failed",
    )
    client.login(username="admin_notify", password="AdminStrongPass9!")

    response = client.get(reverse("notifications_log"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "a@b.com" in content
    assert "c@d.com" in content
    # The failed row should offer a retry button; the sent row should not.
    assert content.count('class="btn-modern btn-retry"') == 1


# ---------------------------------------------------------------------------
# Retry endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_retry_endpoint_re_sends_and_flips_status(client, admin_user):
    failed = Notification.objects.create(
        type="status_change", subject="S", message="M",
        recipient="target@test.com", status="failed",
    )
    client.login(username="admin_notify", password="AdminStrongPass9!")

    with patch("apps.notifications.senders.send_mail") as mock_send:
        response = client.post(reverse("notifications_retry", args=[failed.pk]))

    assert mock_send.called
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"

    failed.refresh_from_db()
    assert failed.status == "sent"


@pytest.mark.django_db
def test_retry_endpoint_rejects_non_admin(client, citizen_user):
    failed = Notification.objects.create(
        type="status_change", subject="S", message="M",
        recipient="t@t.com", status="failed",
    )
    client.login(username="citizen", password="citizen123")

    response = client.post(reverse("notifications_retry", args=[failed.pk]))

    assert response.status_code == 403
    failed.refresh_from_db()
    assert failed.status == "failed"


# ---------------------------------------------------------------------------
# Bulk retry
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bulk_retry_reruns_every_failed_row(client, admin_user):
    for i in range(3):
        Notification.objects.create(
            type="status_change", subject="S", message="M",
            recipient=f"r{i}@test.com", status="failed",
        )
    Notification.objects.create(
        type="status_change", subject="S", message="M",
        recipient="sent@test.com", status="sent",
    )
    client.login(username="admin_notify", password="AdminStrongPass9!")

    with patch("apps.notifications.senders.send_mail") as mock_send:
        response = client.post(reverse("notifications_retry_all_failed"))

    assert response.status_code == 200
    body = response.json()
    assert body["retried"] == 3
    assert body["succeeded"] == 3
    assert body["still_failed"] == 0
    assert mock_send.call_count == 3  # the "sent" row is not re-attempted
