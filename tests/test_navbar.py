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
    submit_link = reverse("submit_report")

    assert 'class="nav-link" href="/">Дома</a>' not in content
    assert "Мапа" in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' in content
    assert "Мои пријави" in content
    assert "Профил" in content
    assert "Одјава" in content
    assert "Најава" not in content
    assert "Регистрација" not in content


@pytest.mark.django_db
def test_officer_navbar(client, officer_user):
    client.login(username="officer", password="officer123")
    response = client.get(reverse("home"))
    content = response.content.decode()
    submit_link = reverse("submit_report")

    assert 'class="nav-link" href="/">Дома</a>' not in content
    assert "Мапа" in content
    assert "Работен панел" in content
    assert "Профил" in content
    assert "Одјава" in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' not in content
    assert "Најава" not in content
    assert "Регистрација" not in content


@pytest.mark.django_db
def test_admin_navbar(client, admin_user):
    client.login(username="admin", password="admin123")
    response = client.get(reverse("home"))
    content = response.content.decode()
    submit_link = reverse("submit_report")

    assert 'class="nav-link" href="/">Дома</a>' not in content
    assert "Мапа" in content
    assert "Админ панел" in content
    assert "Профил" in content
    assert "Одјава" in content
    assert f'class="dropdown-item" href="{submit_link}">Поднеси пријава</a>' not in content
    assert "Најава" not in content
    assert "Регистрација" not in content