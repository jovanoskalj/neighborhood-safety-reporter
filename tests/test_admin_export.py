import csv
import io

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.reports.models import Report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        username="admin_test", password="pass", is_superuser=True, is_staff=True
    )
    return user


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(username="citizen_test", password="pass")


@pytest.fixture
def sample_report(db, regular_user):
    return Report.objects.create(
        citizen=regular_user,
        description="Test report description",
        category="infrastructure",
        priority="normal",
        status="new",
        sector="infrastructure",
        latitude="41.9961",
        longitude="21.4316",
    )


# ---------------------------------------------------------------------------
# T-23 — Admin actions
# ---------------------------------------------------------------------------


def test_admin_can_deactivate_user(client, admin_user, regular_user):
    client.force_login(admin_user)
    url = reverse("toggle_user_active", args=[regular_user.id])
    response = client.post(url)
    regular_user.refresh_from_db()
    assert response.status_code in (200, 302)
    assert regular_user.is_active is False


def test_admin_can_reactivate_user(client, admin_user, regular_user):
    regular_user.is_active = False
    regular_user.save()
    client.force_login(admin_user)
    url = reverse("toggle_user_active", args=[regular_user.id])
    response = client.post(url)
    regular_user.refresh_from_db()
    assert response.status_code in (200, 302)
    assert regular_user.is_active is True


def test_admin_cannot_deactivate_self(client, admin_user):
    client.force_login(admin_user)
    url = reverse("toggle_user_active", args=[admin_user.id])
    client.post(url)
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


def test_non_admin_cannot_toggle_user(client, regular_user, db):
    other = User.objects.create_user(username="other", password="pass")
    client.force_login(regular_user)
    url = reverse("toggle_user_active", args=[other.id])
    response = client.post(url)
    assert response.status_code in (302, 403)
    other.refresh_from_db()
    assert other.is_active is True


# ---------------------------------------------------------------------------
# T-24 — CSV export
# ---------------------------------------------------------------------------


def test_csv_export_returns_valid_file(client, admin_user, sample_report):
    client.force_login(admin_user)
    url = reverse("export_reports_csv")
    response = client.get(url)
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    content = response.content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) >= 1


def test_csv_export_contains_correct_headers(client, admin_user, sample_report):
    client.force_login(admin_user)
    url = reverse("export_reports_csv")
    response = client.get(url)
    content = response.content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    expected = {"id", "citizen", "category", "sector", "status", "priority", "created_at"}
    assert expected.issubset(set(reader.fieldnames))


def test_csv_export_all_reports_present(client, admin_user, regular_user):
    client.force_login(admin_user)
    url = reverse("export_reports_csv")
    response = client.get(url)
    content = response.content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == Report.objects.count()


def test_non_admin_cannot_export(client, regular_user):
    client.force_login(regular_user)
    url = reverse("export_reports_csv")
    response = client.get(url)
    assert response.status_code in (302, 403)


def test_unauthenticated_cannot_export(client):
    url = reverse("export_reports_csv")
    response = client.get(url)
    assert response.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Analytics accuracy
# ---------------------------------------------------------------------------


def test_total_reports_matches_db(client, admin_user, regular_user):
    for i in range(3):
        Report.objects.create(
            citizen=regular_user,
            description=f"Report {i}",
            category="other",
            priority="normal",
            status="new",
            sector="admin",
            latitude="41.99",
            longitude="21.43",
        )
    client.force_login(admin_user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    total_in_db = Report.objects.count()
    assert response.context["stats"]["total_reports"] == total_in_db


def test_resolve_rate_matches_db(client, admin_user, regular_user):
    Report.objects.create(
        citizen=regular_user,
        description="r1",
        category="other",
        priority="normal",
        status="resolved",
        sector="admin",
        latitude="41.99",
        longitude="21.43",
    )
    Report.objects.create(
        citizen=regular_user,
        description="r2",
        category="other",
        priority="normal",
        status="new",
        sector="admin",
        latitude="41.99",
        longitude="21.43",
    )
    client.force_login(admin_user)
    response = client.get(reverse("dashboard"))
    total = Report.objects.count()
    resolved = Report.objects.filter(status="resolved").count()
    expected_rate = round((resolved / total) * 100, 1)
    assert response.context["stats"]["resolve_rate"] == expected_rate


def test_active_users_matches_db(client, admin_user):
    client.force_login(admin_user)
    response = client.get(reverse("dashboard"))
    active_in_db = User.objects.filter(is_active=True).count()
    assert response.context["stats"]["active_users"] == active_in_db


# ---------------------------------------------------------------------------
# Non-admin cannot access admin endpoints
# ---------------------------------------------------------------------------


def test_citizen_redirected_from_dashboard(client, regular_user):
    client.force_login(regular_user)
    response = client.get(reverse("dashboard"))
    assert response.status_code in (302, 403)


def test_officer_redirected_from_dashboard(client, db):
    officer_group, _ = Group.objects.get_or_create(name="officers")
    officer = User.objects.create_user(username="officer1", password="pass")
    officer.groups.add(officer_group)
    client.force_login(officer)
    response = client.get(reverse("dashboard"))
    assert response.status_code in (302, 403)


def test_citizen_cannot_create_category(client, regular_user):
    client.force_login(regular_user)
    response = client.post(reverse("create_category"), {"name": "Hack", "key": "hack"})
    assert response.status_code in (302, 403)


def test_citizen_cannot_delete_user(client, regular_user, db):
    target = User.objects.create_user(username="target", password="pass")
    client.force_login(regular_user)
    response = client.post(reverse("delete_user", args=[target.id]))
    assert response.status_code in (302, 403)
    assert User.objects.filter(id=target.id).exists()