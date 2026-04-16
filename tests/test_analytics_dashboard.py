import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group

@pytest.fixture
def admin_user(db):
    group, _ = Group.objects.get_or_create(name='admin')
    user = User.objects.create_user(username='admin', password='password')
    user.groups.add(group)
    return user

@pytest.fixture
def citizen_user(db):
    group, _ = Group.objects.get_or_create(name='citizen')
    user = User.objects.create_user(username='citizen', password='password')
    user.groups.add(group)
    return user

@pytest.mark.django_db
def test_dashboard_access_for_admin(client, admin_user):
    client.force_login(admin_user)
    response = client.get(reverse('analytics:dashboard'))
    assert response.status_code == 200
    assert 'Аналитички Панел' in response.content.decode()

@pytest.mark.django_db
def test_dashboard_access_denied_for_citizen(client, citizen_user):
    client.force_login(citizen_user)
    response = client.get(reverse('analytics:dashboard'))
    # django's user_passes_test redirects to login by default if test fails
    assert response.status_code == 302
    assert '/accounts/login/' in response.url
