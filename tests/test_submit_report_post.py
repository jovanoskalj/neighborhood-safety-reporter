"""POST-path coverage for the report submission form (task T-10).

The GET-path assertions live in ``test_submit_report_access.py``.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.reports.forms import ReportSubmissionForm
from apps.reports.models import Report


VALID_PAYLOAD = {
    "description": "Голема дупка пред училиштето.",
    "category": "infrastructure",
    "priority": "urgent",
    "municipality": "aerodrom",
    "latitude": "41.998100",
    "longitude": "21.425400",
}


@pytest.mark.django_db
def test_post_creates_report_and_redirects(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(reverse("submit_report"), data=VALID_PAYLOAD)

    assert response.status_code == 302
    assert response.url == reverse("submit_report")
    assert Report.objects.count() == 1

    report = Report.objects.get()
    assert report.citizen == citizen_user
    assert report.category == "infrastructure"
    assert report.priority == "urgent"
    assert report.municipality == "aerodrom"
    assert str(report.latitude) == "41.998100"
    assert report.status == "new"  # default — AI pipeline (T-12) updates later


@pytest.mark.django_db
def test_post_requires_authentication(client):
    response = client.post(reverse("submit_report"), data=VALID_PAYLOAD)

    assert response.status_code == 302
    assert reverse("login") in response.url
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_post_rejects_category_not_in_model_choices(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    payload = {**VALID_PAYLOAD, "category": "road"}  # legacy/invalid value

    response = client.post(reverse("submit_report"), data=payload)

    assert response.status_code == 200
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_post_rejects_missing_coordinates(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    payload = {**VALID_PAYLOAD}
    payload.pop("latitude")
    payload.pop("longitude")

    response = client.post(reverse("submit_report"), data=payload)

    assert response.status_code == 200
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_post_rejects_missing_municipality(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    payload = {**VALID_PAYLOAD}
    payload.pop("municipality")

    response = client.post(reverse("submit_report"), data=payload)

    assert response.status_code == 200
    assert Report.objects.count() == 0


@pytest.mark.django_db
def test_form_rejects_non_image_upload():
    upload = SimpleUploadedFile("malicious.txt", b"not an image", content_type="text/plain")
    form = ReportSubmissionForm(data=VALID_PAYLOAD, files={"image": upload})

    assert not form.is_valid()
    assert "image" in form.errors


@pytest.mark.django_db
def test_post_accepts_high_precision_coordinates(client, citizen_user):
    """Leaflet emits ~14-digit lat/lng; the form must quantize, not reject."""
    client.login(username="citizen", password="citizen123")
    payload = {
        **VALID_PAYLOAD,
        "latitude": "41.99812345678912",
        "longitude": "21.42543210987654",
    }

    response = client.post(reverse("submit_report"), data=payload)

    assert response.status_code == 302
    assert Report.objects.count() == 1
    report = Report.objects.get()
    assert str(report.latitude) == "41.998123"
    assert str(report.longitude) == "21.425432"
