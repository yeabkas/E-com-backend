import pytest
import io
import base64
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import User


def create_test_image_bytes(format='JPEG', color='blue', size=(200, 200)):
    img = Image.new('RGB', size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        email='testuser@example.com',
        password='testpassword123',
        first_name='Test',
        last_name='User',
        role='ADMIN',
    )


@pytest.mark.django_db
class TestProfilePictureAPI:
    def test_anonymous_cannot_upload_avatar(self, api_client):
        res = api_client.post('/api/v1/auth/me/profile-picture/', {})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_upload_profile_picture_multipart_file(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)
        raw_bytes = create_test_image_bytes(format='JPEG')
        uploaded = SimpleUploadedFile(
            name='avatar.jpg',
            content=raw_bytes,
            content_type='image/jpeg'
        )

        res = api_client.post(
            '/api/v1/auth/me/profile-picture/',
            {'profile_picture': uploaded},
            format='multipart'
        )

        assert res.status_code == status.HTTP_200_OK
        data = res.data
        assert data['profile_picture'] is not None
        assert data['profile_picture'].startswith('data:image/jpeg;base64,')

        auth_user.refresh_from_db()
        assert auth_user.profile_picture_data is not None
        assert auth_user.profile_picture_data.startswith('data:image/jpeg;base64,')

    def test_upload_profile_picture_base64_json(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)
        raw_bytes = create_test_image_bytes(format='PNG', color='red', size=(150, 150))
        b64 = base64.b64encode(raw_bytes).decode('utf-8')
        data_uri = f'data:image/png;base64,{b64}'

        res = api_client.post(
            '/api/v1/auth/me/profile-picture/',
            {'profile_picture': data_uri},
            format='json'
        )

        assert res.status_code == status.HTTP_200_OK
        data = res.data
        assert data['profile_picture'] is not None
        assert 'base64,' in data['profile_picture']

        auth_user.refresh_from_db()
        assert auth_user.profile_picture_data is not None

    def test_delete_profile_picture(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)
        auth_user.profile_picture_data = 'data:image/jpeg;base64,abc123'
        auth_user.save()

        res = api_client.delete('/api/v1/auth/me/profile-picture/')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['profile_picture'] is None

        auth_user.refresh_from_db()
        assert auth_user.profile_picture_data is None
        assert not auth_user.profile_picture

