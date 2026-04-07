import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_submit_report_redirects_guest_to_login(client):
    response = client.get(reverse("submit_report"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_submit_report_is_accessible_for_logged_user(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("submit_report"))
    assert response.status_code == 200
    assert "Поднеси пријава" in response.content.decode()
