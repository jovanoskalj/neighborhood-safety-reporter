"""Smoke tests for the admin dashboard."""
from io import StringIO

import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import AuditLog, UserNotification
from apps.reports.models import Report, ReportCategory, Sector


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
    assert 'id="analyticsReportsMap"' in content
    assert 'id="mapGroup"' in content
    assert 'id="filterMunicipality"' in content
    assert 'name="municipality"' in content
    assert reverse("import_reports") in content
    assert reverse("export_reports_excel") in content
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
    initial_count = ReportCategory.objects.count()
    response = client.post(reverse("create_category"), {"key": "x", "name": "X"})

    # user_passes_test redirects unauthorized callers back to LOGIN_URL
    assert response.status_code == 302
    # Should not add a new category
    assert ReportCategory.objects.count() == initial_count


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


@pytest.mark.django_db
def test_admin_creates_worker_with_assignment_and_forced_password_change(client, admin_with_profile):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("create_user"),
        {
            "email": "worker@test.com",
            "password": "WorkerStrongPass9!",
            "role": "officer",
            "sector": "health",
            "municipality": "centar",
        },
    )

    assert response.status_code == 302
    worker = User.objects.get(email="worker@test.com")
    assert worker.username == "worker"
    assert worker.profile.role == "officer"
    assert worker.profile.sector == "health"
    assert worker.profile.municipality == "centar"
    assert worker.profile.must_change_password is True
    assert worker.groups.filter(name="officer").exists()


@pytest.mark.django_db
def test_admin_updates_worker_assignment_immediately(client, admin_with_profile, citizen_user):
    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("update_user", args=[citizen_user.id]),
        {
            "role": "officer",
            "sector": "utilities",
            "municipality": "karposh",
        },
    )

    assert response.status_code == 302
    citizen_user.refresh_from_db()
    assert citizen_user.profile.role == "officer"
    assert citizen_user.profile.sector == "utilities"
    assert citizen_user.profile.municipality == "karposh"
    assert citizen_user.groups.filter(name="officer").exists()


@pytest.mark.django_db
def test_worker_only_sees_assigned_municipality(client, admin_with_profile, citizen_user):
    worker = User.objects.create_user(
        username="worker_user",
        email="worker2@test.com",
        password="WorkerStrongPass9!",
    )
    profile = worker.profile
    profile.role = "officer"
    profile.sector = "health"
    profile.municipality = "centar"
    profile.save()

    visible_report = Report.objects.create(
        citizen=citizen_user,
        description="Clinic sidewalk issue",
        latitude=41.99,
        longitude=21.43,
        category="health",
        priority="normal",
        status="new",
        sector="health",
        municipality="centar",
        ai_processed=True,
    )
    hidden_report = Report.objects.create(
        citizen=citizen_user,
        description="Clinic issue in another municipality",
        latitude=41.98,
        longitude=21.41,
        category="health",
        priority="normal",
        status="new",
        sector="health",
        municipality="karposh",
        ai_processed=True,
    )

    client.login(username="worker_user", password="WorkerStrongPass9!")
    response = client.get(reverse("reports_api"))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert visible_report.id in ids
    assert hidden_report.id not in ids


@pytest.mark.django_db
def test_users_tab_filters_users_by_role(client, admin_with_profile, citizen_user, officer_user):
    officer_profile = officer_user.profile
    officer_profile.role = "officer"
    officer_profile.sector = "health"
    officer_profile.municipality = "centar"
    officer_profile.save()

    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.get(reverse("dashboard") + "?tab=users&role=officer")
    content = response.content.decode()

    assert response.status_code == 200
    assert "@officer" in content
    assert "@citizen" not in content
    assert "@admin_user" not in content
    assert "Работници" in content


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


@pytest.mark.django_db
def test_csv_export_includes_filtered_report_columns(client, admin_with_profile, citizen_user):
    included = Report.objects.create(
        citizen=citizen_user,
        description="Broken hydrant",
        latitude=41.99,
        longitude=21.43,
        category="utilities",
        priority="urgent",
        status="new",
        sector="utilities",
        municipality="centar",
    )
    Report.objects.create(
        citizen=citizen_user,
        description="Park issue",
        latitude=41.98,
        longitude=21.41,
        category="safety",
        priority="low",
        status="resolved",
        sector="safety",
        municipality="karposh",
    )

    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.get(reverse("export_reports_csv") + "?category=utilities")
    content = response.content.decode()

    assert "id,description,category,priority,status,sector,location" in content
    assert f"{included.id},Broken hydrant,utilities,urgent,new,utilities" in content
    assert "Park issue" not in content


@pytest.mark.django_db
def test_import_reports_validates_duplicates_and_invalid_rows(client, admin_with_profile):
    existing = Report.objects.create(
        citizen=admin_with_profile,
        description="Existing row",
        latitude=41.99,
        longitude=21.43,
        category="utilities",
        priority="normal",
        status="new",
        sector="utilities",
    )
    csv_buffer = StringIO()
    csv_buffer.write("id,description,category,priority,status,sector,location,municipality\n")
    csv_buffer.write(f"{existing.id},Duplicate,utilities,normal,new,utilities,\"41.1,21.1\",centar\n")
    csv_buffer.write("9999,Imported row,safety,urgent,new,safety,\"41.2,21.2\",karposh\n")
    csv_buffer.write(",Bad row,unknown,urgent,new,safety,\"41.3,21.3\",karposh\n")
    upload = SimpleUploadedFile("reports.csv", csv_buffer.getvalue().encode("utf-8"), content_type="text/csv")

    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(reverse("import_reports"), {"file": upload})

    assert response.status_code == 302
    assert Report.objects.filter(pk=9999, description="Imported row").exists()
    assert Report.objects.filter(description="Duplicate").count() == 0
    assert Report.objects.filter(description="Bad row").count() == 0


@pytest.mark.django_db
def test_admin_classification_notifies_assigned_worker(client, admin_with_profile, citizen_user, officer_user):
    officer_profile = officer_user.profile
    officer_profile.role = "officer"
    officer_profile.sector = "safety"
    officer_profile.municipality = "aerodrom"
    officer_profile.save()
    report = Report.objects.create(
        citizen=citizen_user,
        description="Needs classification",
        latitude=41.99,
        longitude=21.43,
        category="other",
        priority="normal",
        status="unclassified",
        sector="admin",
        municipality="berovo",
    )

    client.login(username="admin_user", password="AdminStrongPass9!")
    response = client.post(
        reverse("classify_report", args=[report.id]),
        {"category": "safety", "priority": "urgent", "sector": "safety"},
    )

    assert response.status_code == 302
    report.refresh_from_db()
    assert report.category == "safety"
    assert report.sector == "safety"
    assert UserNotification.objects.filter(
        user=officer_user,
        report=report,
        type="report_assigned",
        title__icontains="класифицирана",
    ).exists()
    assert UserNotification.objects.filter(
        user=citizen_user,
        report=report,
        type="system",
        title__icontains="класифицирана",
    ).exists()
