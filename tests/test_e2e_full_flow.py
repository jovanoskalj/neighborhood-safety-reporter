"""End-to-End full flow regression tests (T-32)."""
import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.urls import reverse
from django.test import override_settings

from apps.accounts.models import EmailVerificationCode, UserProfile
from apps.reports.models import Report


@pytest.fixture
def test_password():
    return "Pass123!"


@pytest.mark.django_db
@override_settings(AI_CLASSIFICATION_ENABLED=True)
def test_full_happy_path(client, test_password):
    """
    Test full flow: registration -> verification -> submission -> resolution -> notification.
    """
    # 1. Registration
    reg_data = {
        "username": "citizen_e2e",
        "email": "citizen_e2e@example.com",
        "password1": test_password,
        "password2": test_password,
        "phone": "070123456",
    }
    response = client.post(reverse("register"), reg_data)
    assert response.status_code == 302
    assert response.url == reverse("verify_email_code")

    user = User.objects.get(username="citizen_e2e")
    assert not user.is_active

    # 2. Email Verification
    # In test environment, SENDGRID_ENABLED is False, so it uses settings.DEV_VERIFICATION_CODE or DB record
    verification = EmailVerificationCode.objects.get(user=user)
    response = client.post(reverse("verify_email_code"), {"code": verification.code})
    assert response.status_code == 302
    assert response.url == reverse("login")

    user.refresh_from_db()
    assert user.is_active

    # 3. Report Submission
    client.login(username="citizen_e2e", password=test_password)
    with patch("apps.reports.signals.classify_report") as mock_classify:
        mock_classify.return_value = {
            "category": "infrastructure",
            "priority": "normal",
            "sector": "infrastructure",
        }
        report_data = {
            "description": "Large pothole blocking traffic",
            "latitude": 41.9965,
            "longitude": 21.4312,
            "category": "infrastructure",
            "priority": "normal",
            "municipality": "centar",
        }
        response = client.post(reverse("submit_report"), report_data)
    
    assert response.status_code == 302
    report = Report.objects.get(description="Large pothole blocking traffic")
    assert report.status == "new"
    assert report.sector == "infrastructure"
    assert report.citizen == user

    # 4. Officer Resolution
    # Setup officer
    officer = User.objects.create_user(username="officer_e2e", password=test_password)
    group, _ = Group.objects.get_or_create(name="officer")
    officer.groups.add(group)
    UserProfile.objects.filter(user=officer).update(role="officer", sector="infrastructure")
    
    client.login(username="officer_e2e", password=test_password)
    
    # Check officer can see the report
    response = client.get(reverse("officer_panel"))
    assert "Large pothole blocking traffic" in response.content.decode()

    # Update status to resolved
    patch_data = {
        "status": "resolved",
        "internal_note": "Pothole filled and road cleared.",
    }
    response = client.patch(
        reverse("update_report_status", args=[report.pk]),
        data=json.dumps(patch_data),
        content_type="application/json",
    )
    assert response.status_code == 200
    
    report.refresh_from_db()
    assert report.status == "resolved"
    assert report.assigned_officer == officer

    # 5. Notification (Email)
    # Check if status change email was sent
    assert len(mail.outbox) > 0
    # Last email should be the status change one
    status_email = mail.outbox[-1]
    assert "citizen_e2e@example.com" in status_email.to
    assert "решена" in status_email.body or "resolved" in status_email.body.lower()


@pytest.mark.django_db
@override_settings(AI_CLASSIFICATION_ENABLED=True)
def test_ai_classification_failure_fallback(client, test_password):
    """
    Verify that if AI classification fails, the report is still created with 'unclassified' status.
    """
    citizen = User.objects.create_user(username="citizen_fail", password=test_password, is_active=True)
    client.login(username="citizen_fail", password=test_password)
    
    with patch("apps.reports.signals.classify_report") as mock_classify:
        # Simulate AI timeout or error
        mock_classify.side_effect = Exception("Ollama connection failed")
        
        report_data = {
            "description": "Suspicious activity in the park",
            "latitude": 41.9876,
            "longitude": 21.4567,
            "category": "safety",
            "priority": "normal",
            "municipality": "aerodrom",
        }
        response = client.post(reverse("submit_report"), report_data)
        
    assert response.status_code == 302
    report = Report.objects.get(description="Suspicious activity in the park")
    assert report.status == "unclassified"
    assert not report.ai_processed


@pytest.mark.django_db
def test_officer_dashboard_redirect(client, test_password):
    """
    Officers should be redirected to the officer panel if they try to access the admin dashboard.
    """
    officer = User.objects.create_user(username="officer_redirect", password=test_password, is_active=True)
    group, _ = Group.objects.get_or_create(name="officer")
    officer.groups.add(group)
    UserProfile.objects.filter(user=officer).update(role="officer")
    
    client.login(username="officer_redirect", password=test_password)
    response = client.get(reverse("dashboard"))
    
    assert response.status_code == 302
    assert response.url == reverse("officer_panel")


@pytest.mark.django_db
def test_admin_export_reports(client, test_password):
    """
    Admins can export reports to CSV.
    """
    admin = User.objects.create_user(username="admin_test", password=test_password, is_active=True, is_staff=True)
    group, _ = Group.objects.get_or_create(name="admin")
    admin.groups.add(group)
    UserProfile.objects.filter(user=admin).update(role="admin")
    
    # Create some data to export
    Report.objects.create(
        citizen=admin,
        description="Test report for export",
        latitude=42.0,
        longitude=21.0,
        category="other"
    )
    
    client.login(username="admin_test", password=test_password)
    response = client.get(reverse("export_reports"))
    
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "Test report for export" in response.content.decode()
