import pytest
from django.contrib.auth.models import User, Group


@pytest.fixture
def citizen_user(db):
    group, _ = Group.objects.get_or_create(name='citizen')
    user = User.objects.create_user(username='citizen', email='citizen@test.com', password='citizen123')
    user.groups.add(group)
    return user


@pytest.fixture
def officer_user(db):
    group, _ = Group.objects.get_or_create(name='officer')
    user = User.objects.create_user(username='officer', email='officer@test.com', password='officer123')
    user.groups.add(group)
    return user


@pytest.fixture
def admin_user(db):
    group, _ = Group.objects.get_or_create(name='admin')
    user = User.objects.create_user(username='admin', email='admin@test.com', password='admin123')
    user.groups.add(group)
    return user
