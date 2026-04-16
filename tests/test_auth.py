import pytest
from datetime import timedelta
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from apps.accounts.models import EmailVerificationCode


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
    assert "Невалидни податоци за најава." in response.content.decode()


@pytest.mark.django_db
def test_logout(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("logout"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_register_user(mock_send_mail, client):
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
    assert response.url == reverse("verify_email_code")
    user = User.objects.get(username="new_user")
    assert user.is_active is False
    assert EmailVerificationCode.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_verify_email_code_activates_user(client):
    user = User.objects.create_user(
        username="pending_user",
        email="pending@test.com",
        password="pending123",
        is_active=False,
    )
    EmailVerificationCode.objects.create(
        user=user,
        code="123456",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    session = client.session
    session["pending_verification_user_id"] = user.id
    session.save()

    response = client.post(reverse("verify_email_code"), {"code": "123456"})
    assert response.status_code == 302
    assert response.url == reverse("login")

    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_register_and_verify_email(client):
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
    assert response.url == reverse("verify_email_code")

    user = User.objects.get(username="new_user")
    assert user.is_active is False

    verification = EmailVerificationCode.objects.get(user=user)
    assert verification.code is not None


@pytest.mark.django_db
def test_login_logout(client, citizen_user):
    login_response = client.post(reverse("login"), {
        "username": "citizen",
        "password": "citizen123"
    })

    assert login_response.status_code == 302
    assert client.session.get("_auth_user_id") is not None

    logout_response = client.get(reverse("logout"))

    assert logout_response.status_code == 302
    assert client.session.get("_auth_user_id") is None