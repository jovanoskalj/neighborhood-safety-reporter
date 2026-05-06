"""Auth-path tests covering the register → verify → login → logout cycle (T-13)."""
import re
from unittest.mock import patch

import pytest
from datetime import timedelta
from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.utils import timezone

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
def test_login_page_has_forgot_password_link(client):
    response = client.get(reverse("login"))
    content = response.content.decode()
    assert reverse("password_reset") in content


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
def test_verify_email_code_activates_user(client, settings):
    """Posting the DEV verification code activates the pending user."""
    settings.SENDGRID_ENABLED = False
    settings.DEV_VERIFICATION_CODE = "111111"

    user = User.objects.create_user(
        username="pending_user",
        email="pending@test.com",
        password="pending123",
        is_active=False,
    )

    EmailVerificationCode.objects.create(
        user=user,
        code="111111",
        expires_at=timezone.now() + timedelta(minutes=15),
    )

    session = client.session
    session["pending_verification_user_id"] = user.id
    session.save()

    response = client.post(
        reverse("verify_email_code"),
        {"code": "111111"},
    )

    user.refresh_from_db()

    assert response.status_code == 302
    assert response.url == reverse("login")
    assert user.is_active is True


@pytest.mark.django_db
def test_register_and_verify_email(client):
    """Registration creates an inactive user plus a verification record."""
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
    """Login establishes a session; logout clears it."""
    login_response = client.post(reverse("login"), {
        "username": "citizen",
        "password": "citizen123"
    })

    assert login_response.status_code == 302
    assert client.session.get("_auth_user_id") is not None

    logout_response = client.get(reverse("logout"))

    assert logout_response.status_code == 302
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
@patch("apps.accounts.views.send_mail")
def test_register_sends_email(mock_send_mail, client, settings):
    """Registration triggers a verification email when SENDGRID is enabled."""
    settings.SENDGRID_ENABLED = True

    response = client.post(reverse("register"), {
        "username": "testuser",
        "email": "test@test.com",
        "password1": "StrongPass123",
        "password2": "StrongPass123",
        "role": "citizen",
        "sector": "",
        "phone": "",
    })

    assert response.status_code == 302
    mock_send_mail.assert_called_once()


@pytest.mark.django_db
def test_profile_page_loads_for_authenticated_user(client):
    user = User.objects.create_user(
        username="citizen123",
        email="citizen123@example.com",
        password="StrongPass123!",
    )
    client.login(username="citizen123", password="StrongPass123!")

    response = client.get(reverse("profile"))

    assert response.status_code == 200
    content = response.content.decode()

    assert "citizen123@example.com" in content
    assert 'name="profile-first_name"' in content
    assert 'name="profile-last_name"' in content
    assert 'name="profile-email"' in content


@pytest.mark.django_db
def test_profile_form_saves_basic_info(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(
        reverse("profile"),
        {
            "save_profile": "1",
            "profile-first_name": "Petar",
            "profile-last_name": "Petrovski",
            "profile-email": "petar@test.com",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Профилот е успешно ажуриран." in response.content.decode()
    citizen_user.refresh_from_db()
    assert citizen_user.first_name == "Petar"
    assert citizen_user.last_name == "Petrovski"
    assert citizen_user.email == "petar@test.com"


@pytest.mark.django_db
def test_profile_form_allows_changing_email_to_unique_value(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(
        reverse("profile"),
        {
            "save_profile": "1",
            "profile-first_name": "Citizen",
            "profile-last_name": "User",
            "profile-email": "citizen+new@test.com",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Профилот е успешно ажуриран." in response.content.decode()
    citizen_user.refresh_from_db()
    assert citizen_user.email == "citizen+new@test.com"


@pytest.mark.django_db
def test_password_change_success(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(
        reverse("profile"),
        {
            "change_password": "1",
            "password-old_password": "citizen123",
            "password-new_password1": "newstrongpass123",
            "password-new_password2": "newstrongpass123",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert "Лозинката е успешно променета." in response.content.decode()
    citizen_user.refresh_from_db()
    assert citizen_user.check_password("newstrongpass123")


@pytest.mark.django_db
def test_login_with_new_password_after_change(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    client.post(
        reverse("profile"),
        {
            "change_password": "1",
            "password-old_password": "citizen123",
            "password-new_password1": "newstrongpass123",
            "password-new_password2": "newstrongpass123",
        },
        follow=True,
    )

    client.get(reverse("logout"))
    login_response = client.post(
        reverse("login"),
        {"username": "citizen", "password": "newstrongpass123"},
    )
    assert login_response.status_code == 302


@pytest.mark.django_db
def test_login_with_email_after_password_change(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    client.post(
        reverse("profile"),
        {
            "change_password": "1",
            "password-old_password": "citizen123",
            "password-new_password1": "newstrongpass123",
            "password-new_password2": "newstrongpass123",
        },
        follow=True,
    )

    client.get(reverse("logout"))
    login_response = client.post(
        reverse("login"),
        {"username": "citizen@test.com", "password": "newstrongpass123"},
    )
    assert login_response.status_code == 302


@pytest.mark.django_db
def test_password_change_shows_validation_errors(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.post(
        reverse("profile"),
        {
            "change_password": "1",
            "password-old_password": "wrong-old-password",
            "password-new_password1": "newstrongpass123",
            "password-new_password2": "newstrongpass123",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    citizen_user.refresh_from_db()
    assert citizen_user.check_password("citizen123")
    assert not citizen_user.check_password("newstrongpass123")
    assert "name=\"password-old_password\"" in content
    # assert "text-danger small mt-1" in content


@pytest.mark.django_db
def test_password_reset_flow_updates_password(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    user = User.objects.create_user(
        username="reset_user",
        email="reset.user@test.com",
        password="oldpass123",
        is_active=True,
    )

    reset_response = client.post(reverse("password_reset"), {"email": user.email})
    assert reset_response.status_code == 302
    assert reset_response.url == reverse("password_reset_done")

    assert len(mail.outbox) == 1
    email_body = mail.outbox[0].body
    match = re.search(r"http://testserver(?P<path>/accounts/reset/[^\s]+)", email_body)
    assert match is not None

    reset_link = match.group("path")
    confirm_get = client.get(reset_link)
    assert confirm_get.status_code == 302

    set_password_link = confirm_get.url
    confirm_form_get = client.get(set_password_link)
    assert confirm_form_get.status_code == 200

    confirm_post = client.post(
        set_password_link,
        {
            "new_password1": "newpass1234",
            "new_password2": "newpass1234",
        },
    )
    assert confirm_post.status_code == 302
    assert confirm_post.url == reverse("password_reset_complete")

    login_response = client.post(
        reverse("login"),
        {
            "username": "reset_user",
            "password": "newpass1234",
        },
    )
    assert login_response.status_code == 302
