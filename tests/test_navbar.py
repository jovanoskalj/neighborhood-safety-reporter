import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_citizen_navbar(client, citizen_user):
    client.login(username="citizen", password="citizen123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert "Дома" in content
    assert "Најава" in content
    assert "Регистрација" in content
    assert "Поднеси пријава" in content


@pytest.mark.django_db
def test_officer_navbar(client, officer_user):
    client.login(username="officer", password="officer123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert "Дома" in content
    assert "Најава" in content
    assert "Регистрација" in content
    assert "Поднеси пријава" in content


@pytest.mark.django_db
def test_admin_navbar(client, admin_user):
    client.login(username="admin", password="admin123")
    response = client.get(reverse("home"))
    content = response.content.decode()

    assert "Дома" in content
    assert "Најава" in content
    assert "Регистрација" in content
    assert "Поднеси пријава" in content