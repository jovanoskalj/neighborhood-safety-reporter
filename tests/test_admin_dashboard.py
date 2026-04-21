"""Smoke tests for the admin dashboard."""
import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from apps.accounts.models import AuditLog
from apps.reports.models import ReportCategory, Sector


@pytest.fixture
def admin_with_profile(db):
    group, _ = Group.objects.get_or_create(name="admin")
    user = User.objects.create_user(
        username="admin_user",
        email="admin@test.com",
        password="AdminStrongPass9!",
    )
    user.groups.add(group)
    profile = user.profile
    profile.role = "admin"
    profile.save()
    return user


# ---------------------------------------------------------------------------
# Dashboard entry point
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_renders_for_admin(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.get(reverse("dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Аналитика" in content
    assert "Корисници" in content
    assert "Подесувања" in content
    assert "Системски лог" in content


@pytest.mark.django_db
def test_analytics_tab_includes_t27_chart_widgets(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.get(reverse("dashboard") + "?tab=analytics")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'id="timeSeriesChart"' in content
    assert 'id="categoryChart"' in content
    assert 'id="statusChart"' in content
    assert 'id="periodSelect"' in content
    # Period selector exposes all three buckets the API understands.
    for bucket in ("weekly", "monthly", "yearly"):
        assert f'value="{bucket}"' in content
    # Chart.js is loaded on this tab.
    assert "chart.umd.min.js" in content
    # JS fetches the stats API via Django URL reversing.
    assert "/api/analytics/stats/" in content


@pytest.mark.django_db
def test_dashboard_redirects_citizen_to_home(client, citizen_user):
    """Citizens must not be bounced to the login page (old admin-only bug)."""
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response.url == reverse("home")


@pytest.mark.django_db
def test_dashboard_redirects_officer_to_panel(client, officer_user):
    client.login(username="officer", password="officer123")
    response = client.get(reverse("dashboard"))

    assert response.status_code == 302
    assert response.url == reverse("officer_panel")


# ---------------------------------------------------------------------------
# Mutating endpoints are admin-only
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_non_admin_cannot_create_category(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(reverse("create_category"), {"key": "x", "name": "X"})

    # user_passes_test redirects unauthorized callers back to LOGIN_URL
    assert response.status_code == 302
    assert ReportCategory.objects.count() == 0


# ---------------------------------------------------------------------------
# Settings tab: categories + sectors CRUD
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_creates_category_and_logs_it(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("create_category"),
        {"key": "noise", "name": "Бучава", "is_active": "on"},
    )

    assert response.status_code == 302
    assert ReportCategory.objects.filter(key="noise", name="Бучава").exists()
    assert AuditLog.objects.filter(action="create_category").exists()


@pytest.mark.django_db
def test_admin_creates_sector_and_logs_it(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("create_sector"),
        {"key": "transport", "name": "Транспорт", "is_active": "on"},
    )

    assert response.status_code == 302
    assert Sector.objects.filter(key="transport").exists()
    assert AuditLog.objects.filter(action="create_sector").exists()


# ---------------------------------------------------------------------------
# Users tab: toggle + password validation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_toggles_user_active(client, admin_with_profile, citizen_user):
    assert citizen_user.is_active is True
    client.login(username="admin_user", password="AdminStrongPass9!")

    response = client.post(reverse("toggle_user_active", args=[citizen_user.id]))

    assert response.status_code == 302
    citizen_user.refresh_from_db()
    assert citizen_user.is_active is False
    assert AuditLog.objects.filter(action="toggle_user_active", target_id=citizen_user.id).exists()


@pytest.mark.django_db
def test_admin_cannot_deactivate_self(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(reverse("toggle_user_active", args=[admin_with_profile.id]))

    assert response.status_code == 302
    admin_with_profile.refresh_from_db()
    assert admin_with_profile.is_active is True


@pytest.mark.django_db
def test_admin_create_user_rejects_weak_password(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("create_user"),
        {
            "username": "weak_user",
            "email": "weak@test.com",
            "password": "a",  # fails MinimumLengthValidator
            "role": "citizen",
        },
    )

    # Weak password → form invalid → no user created, redirect back to users tab
    assert response.status_code == 302
    assert not User.objects.filter(username="weak_user").exists()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_csv_export_streams_attachment(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.get(reverse("export_reports_csv"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    assert "reports_export.csv" in response["Content-Disposition"]
