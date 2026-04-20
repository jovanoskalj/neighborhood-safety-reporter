import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_guest_navbar(client):
    response = client.get(reverse("home"))
    content = response.content.decode()
    submit_link = reverse("submit_report")

    assert "Безбеден Град" in content
    assert "Република Северна Македонија" in content
    assert 'class="nav-link" href="/">Дома</a>' not in content
    assert "Мапа" not in content
    assert "Најава" in content
    assert "Регистрација" not in content
    assert "Одјава" not in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' not in content


@pytest.mark.django_db
def test_citizen_navbar(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    home_link = reverse("home")
    login_link = reverse("login")
    submit_link = reverse("submit_report")
    map_link = reverse("map_view")
    profile_link = reverse("profile")
    logout_link = reverse("logout")

    assert response.status_code == 200

    assert f'class="nav-link" href="{home_link}">Дома</a>' not in content
    assert f'class="nav-link" href="{map_link}">Мапа</a>' in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' in content
    assert "Мои пријави" in content
    assert f'class="nav-link" href="{profile_link}">Профил</a>' in content
    assert f'class="nav-link nav-link-logout" href="{logout_link}">Одјава</a>' in content
    assert f'href="{login_link}">Најава</a>' not in content
    assert "Регистрација" not in content
    assert "Работен панел" not in content
    assert "Админ панел" not in content


@pytest.mark.django_db
def test_officer_navbar(client, officer_user):
    client.login(username="officer", password="officer123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    home_link = reverse("home")
    login_link = reverse("login")
    submit_link = reverse("submit_report")
    map_link = reverse("map_view")
    officer_panel_link = reverse("officer_panel")
    profile_link = reverse("profile")
    logout_link = reverse("logout")

    assert response.status_code == 200

    assert f'class="nav-link" href="{home_link}">Дома</a>' not in content
    assert f'class="nav-link" href="{map_link}">Мапа</a>' in content
    assert f'class="nav-link" href="{officer_panel_link}">Работен панел</a>' in content
    assert f'class="nav-link" href="{profile_link}">Профил</a>' in content
    assert f'class="nav-link nav-link-logout" href="{logout_link}">Одјава</a>' in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' not in content
    assert f'href="{login_link}">Најава</a>' not in content
    assert "Регистрација" not in content
    assert "Админ панел" not in content


@pytest.mark.django_db
def test_admin_navbar(client, admin_user):
    client.login(username="admin", password="admin123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    home_link = reverse("home")
    login_link = reverse("login")
    submit_link = reverse("submit_report")
    map_link = reverse("map_view")
    profile_link = reverse("profile")
    logout_link = reverse("logout")

    assert response.status_code == 200

    assert f'class="nav-link" href="{home_link}">Дома</a>' not in content
    assert f'class="nav-link" href="{map_link}">Мапа</a>' in content
    assert "Админ панел" in content
    assert f'class="nav-link" href="{profile_link}">Профил</a>' in content
    assert f'class="nav-link nav-link-logout" href="{logout_link}">Одјава</a>' in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' not in content
    assert f'href="{login_link}">Најава</a>' not in content
    assert "Регистрација" not in content
    assert "Работен панел" not in content