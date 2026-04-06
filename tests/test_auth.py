import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch


@pytest.mark.django_db
def test_register_page_loads(client):
    response = client.get(reverse("register"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_page_loads(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_user_login_success(client, citizen_user):
    response = client.post(reverse("login"), {
        "username": "citizen",
        "password": "citizen123"
    })

    assert response.status_code == 302


@pytest.mark.django_db
def test_user_login_fail(client):
    response = client.post(reverse("login"), {
        "username": "wrong",
        "password": "wrong"
    })
    assert response.status_code == 200
    assert b"Invalid credentials" in response.content


@pytest.mark.django_db
def test_logout(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("logout"))
    assert response.status_code == 302


@pytest.mark.django_db
@patch("apps.accounts.views.ActivationMailManager.send_verification_link")
def test_register_user(mock_email, client):
    response = client.post(reverse("register"), {
        "username": "new_user",
        "email": "new.user@test.com",
        "password1": "newuser123",
        "password2": "newuser123",
        "role": "citizen",
        "sector": "",
        "phone": "123456"
    })

    assert response.status_code == 302
