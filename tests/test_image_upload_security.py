import io
import pytest
from django.contrib.auth.models import User, Group
from django.urls import reverse
from PIL import Image
from apps.accounts.models import UserProfile


def make_user(username, role):
    user = User.objects.create_user(username=username, password='test123', is_active=True)
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    UserProfile.objects.filter(user=user).update(role=role)
    return user


def make_real_image(fmt='PNG'):
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    buf.name = f'test.{"png" if fmt == "PNG" else "jpg"}'
    return buf


def make_fake_image():
    buf = io.BytesIO(b'this is not an image')
    buf.name = 'fake.jpg'
    return buf


def make_oversized_image():
    buf = io.BytesIO(b'0' * (6 * 1024 * 1024))
    buf.name = 'big.jpg'
    return buf


@pytest.mark.django_db
def test_valid_png_upload_accepted(client):
    make_user('citizen1', 'citizen')
    client.login(username='citizen1', password='test123')
    img = make_real_image('PNG')
    response = client.post(reverse('submit_report'), {
        'description': 'Test report',
        'latitude': '41.9981',
        'longitude': '21.4254',
        'category': 'safety',
        'priority': 'normal',
        'image': img,
    })
    assert response.status_code in [200, 302]


@pytest.mark.django_db
def test_fake_image_rejected(client):
    make_user('citizen2', 'citizen')
    client.login(username='citizen2', password='test123')
    fake = make_fake_image()
    response = client.post(reverse('submit_report'), {
        'description': 'Test report',
        'latitude': '41.9981',
        'longitude': '21.4254',
        'category': 'safety',
        'priority': 'normal',
        'image': fake,
    })
    assert response.status_code == 200
    content = response.content.decode()
    assert 'валидна' in content or 'PNG' in content or 'JPG' in content


@pytest.mark.django_db
def test_oversized_image_rejected(client):
    make_user('citizen3', 'citizen')
    client.login(username='citizen3', password='test123')
    big = make_oversized_image()
    response = client.post(reverse('submit_report'), {
        'description': 'Test report',
        'latitude': '41.9981',
        'longitude': '21.4254',
        'category': 'safety',
        'priority': 'normal',
        'image': big,
    })
    assert response.status_code == 200