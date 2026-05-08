import pytest
from django.contrib.auth.models import Group, User


def pytest_configure(config):
    """Disable the AI classification post_save signal by default for tests.

    Classification calls an external Ollama service. Leaving the signal active
    would let tests incidentally hit the network (or time out) for every
    ``Report.objects.create()``. Tests that specifically exercise the pipeline
    re-enable it with ``@override_settings(AI_CLASSIFICATION_ENABLED=True)``.
    """
    from django.conf import settings
    settings.AI_CLASSIFICATION_ENABLED = False


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
