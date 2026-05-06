import pytest
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import Client
from apps.accounts.models import UserProfile


def make_user(username, role, is_staff=False):
    user = User.objects.create_user(username=username, password='test123', is_active=True)
    user.is_staff = is_staff
    user.is_superuser = is_staff
    user.save()
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    UserProfile.objects.filter(user=user).update(role=role)
    return user


# --- SECURITY TESTS ---

@pytest.mark.django_db
def test_csrf_protection_on_login():
    """Login form should require CSRF token."""
    client = Client(enforce_csrf_checks=True)
    response = client.post(reverse('login'), {
        'username': 'test',
        'password': 'test'
    })
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_endpoints_blocked_for_guests(client):
    """Unauthenticated users cannot access admin endpoints."""
    urls = [
        reverse('admin_user_list'),
        reverse('admin_system_log'),
        reverse('admin_category_list'),
        reverse('export_reports'),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code in [302, 403], f"{url} should be protected"


@pytest.mark.django_db
def test_admin_endpoints_blocked_for_citizens(client):
    """Citizens cannot access admin endpoints."""
    make_user('citizen1', 'citizen')
    client.login(username='citizen1', password='test123')
    urls = [
        reverse('admin_user_list'),
        reverse('admin_system_log'),
        reverse('admin_category_list'),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code in [302, 403], f"{url} should be blocked for citizens"


@pytest.mark.django_db
def test_admin_endpoints_blocked_for_officers(client):
    """Officers cannot access admin endpoints."""
    make_user('officer1', 'officer')
    client.login(username='officer1', password='test123')
    urls = [
        reverse('admin_user_list'),
        reverse('admin_system_log'),
        reverse('admin_category_list'),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code in [302, 403], f"{url} should be blocked for officers"


@pytest.mark.django_db
def test_xss_in_report_description_is_escaped(client):
    """XSS payload in report description should be escaped in HTML responses."""
    make_user('admin1', 'admin', is_staff=True)
    client.login(username='admin1', password='test123')
    from apps.reports.models import Report
    u = User.objects.get(username='admin1')
    Report.objects.create(
        citizen=u,
        description='<script>alert("xss")</script>',
        latitude=41.9981,
        longitude=21.4254,
        category='safety',
        priority='normal',
        status='new',
        sector='safety'
    )
    response = client.get(reverse('admin_user_list'))
    assert b'<script>alert' not in response.content

@pytest.mark.django_db
def test_passwords_not_in_response(client):
    """Password hashes should never appear in any response."""
    make_user('admin2', 'admin', is_staff=True)
    client.login(username='admin2', password='test123')
    response = client.get(reverse('admin_user_list'))
    assert b'pbkdf2' not in response.content


# --- PERFORMANCE TESTS ---

@pytest.mark.django_db
def test_export_handles_large_dataset(client):
    """Export should handle 100 reports without errors."""
    from apps.reports.models import Report
    u = make_user('admin3', 'admin', is_staff=True)
    reports = [
        Report(
            citizen=u,
            description=f'Report {i}',
            latitude=41.9981,
            longitude=21.4254,
            category='safety',
            priority='normal',
            status='new',
            sector='safety'
        )
        for i in range(100)
    ]
    Report.objects.bulk_create(reports)
    client.login(username='admin3', password='test123')
    response = client.get(reverse('export_reports') + '?format=csv')
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_user_list_handles_many_users(client):
    """Admin user list should handle 50 users without errors."""
    for i in range(50):
        User.objects.create_user(username=f'user{i}', password='test123', is_active=True)
    make_user('admin4', 'admin', is_staff=True)
    client.login(username='admin4', password='test123')
    response = client.get(reverse('admin_user_list'))
    assert response.status_code == 200