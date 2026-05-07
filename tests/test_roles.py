import pytest


@pytest.mark.django_db
def test_citizen_role(citizen_user):
    assert citizen_user.groups.filter(name="citizen").exists()


@pytest.mark.django_db
def test_officer_role(officer_user):
    assert officer_user.groups.filter(name="officer").exists()


@pytest.mark.django_db
def test_admin_role(admin_user):
    assert admin_user.groups.filter(name="admin").exists()
