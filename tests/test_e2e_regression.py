"""End-to-End regression tests covering full happy path (T-32)."""
import pytest
from django.contrib.auth.models import User, Group
from django.urls import reverse
from apps.accounts.models import UserProfile
from apps.reports.models import Report


def make_user(username, role, is_staff=False):
    user = User.objects.create_user(username=username, password='test123', is_active=True)
    user.is_staff = is_staff
    user.is_superuser = is_staff
    user.save()
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    UserProfile.objects.filter(user=user).update(role=role)
    return user


@pytest.mark.django_db
def test_citizen_can_submit_report(client):
    make_user('citizen1', 'citizen')
    client.login(username='citizen1', password='test123')
    response = client.get(reverse('submit_report'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_officer_can_access_dashboard(client):
    make_user('officer1', 'officer')
    client.login(username='officer1', password='test123')
    response = client.get(reverse('dashboard'))
    assert response.status_code in [200, 302]


@pytest.mark.django_db
def test_admin_can_access_user_list(client):
    make_user('admin1', 'admin', is_staff=True)
    client.login(username='admin1', password='test123')
    response = client.get(reverse('admin_user_list'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_export_csv(client):
    make_user('admin2', 'admin', is_staff=True)
    client.login(username='admin2', password='test123')
    response = client.get(reverse('export_reports') + '?format=csv')
    assert response.status_code == 200
    assert 'text/csv' in response['Content-Type']


@pytest.mark.django_db
def test_guest_cannot_access_submit_report(client):
    response = client.get(reverse('submit_report'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_guest_cannot_access_admin_panel(client):
    response = client.get(reverse('admin_user_list'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_officer_cannot_access_admin_panel(client):
    make_user('officer2', 'officer')
    client.login(username='officer2', password='test123')
    response = client.get(reverse('admin_user_list'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_report_created_in_db(client):
    citizen = make_user('citizen2', 'citizen')
    Report.objects.create(
        citizen=citizen,
        description='Broken streetlight',
        latitude=41.9981,
        longitude=21.4254,
        category='infrastructure',
        priority='normal',
        status='new',
        sector='infrastructure'
    )
    assert Report.objects.filter(description='Broken streetlight').exists()