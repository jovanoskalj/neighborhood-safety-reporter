import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_guest_navbar(client):
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert "Безбеден Град" in content
    assert "Република Северна Македонија" in content
    assert "Најава" in content
    assert "Регистрација" not in content
    assert "Одјава" not in content
    # The Map nav link only renders for authenticated users.
    assert reverse("map_view") not in content


@pytest.mark.django_db
def test_citizen_navbar(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200

    # Citizen sees Map (top nav) and personal links (in user dropdown).
    assert "Мапа" in content
    assert reverse("map_view") in content
    assert "Мои пријави" in content
    assert reverse("submit_report") in content
    assert reverse("profile") in content
    assert reverse("logout") in content
    assert "Одјава" in content

    # Anonymous-only links must not render.
    assert "Најава" not in content
    assert "Регистрација" not in content

    # Citizen must not see officer/admin entry points.
    assert "Работен панел" not in content
    assert "Админ панел" not in content


@pytest.mark.django_db
def test_officer_navbar(client, officer_user):
    client.login(username="officer", password="officer123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200

    # Officer sees Map + their work surfaces.
    assert "Мапа" in content
    assert reverse("map_view") in content
    assert reverse("officer_panel") in content
    assert "Работен панел" in content
    assert reverse("profile") in content
    assert reverse("logout") in content
    assert "Одјава" in content

    # Officer-only: no submit-report dropdown item, no admin panel link.
    assert "Админ панел" not in content
    assert "Најава" not in content
    assert "Регистрација" not in content


@pytest.mark.django_db
def test_admin_navbar(client, admin_user):
    client.login(username="admin", password="admin123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200

    # Admin sees Map + their dashboard entry point.
    assert "Мапа" in content
    assert reverse("map_view") in content
    assert "Админ панел" in content
    assert reverse("profile") in content
    assert reverse("logout") in content
    assert "Одјава" in content

    # Admin-only: no officer panel link, no anonymous links.
    assert "Работен панел" not in content
    assert "Најава" not in content
    assert "Регистрација" not in content
