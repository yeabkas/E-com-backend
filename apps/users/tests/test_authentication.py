import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestLogin:

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('auth-login')
        self.user = UserFactory(email="test@example.com", password="StrongPass123!")

    def test_login_with_valid_credentials(self):
        data = {"email": "test@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == "test@example.com"

    def test_login_with_wrong_password(self):
        data = {"email": "test@example.com", "password": "WrongPassword"}
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_with_nonexistent_email(self):
        data = {"email": "nobody@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_updates_last_login(self):
        data = {"email": "test@example.com", "password": "StrongPass123!"}
        self.client.post(self.url, data, format='json')
        self.user.refresh_from_db()
        assert self.user.last_login_at is not None

    def test_login_with_suspended_account(self):
        self.user.is_suspended = True
        self.user.save()
        data = {"email": "test@example.com", "password": "StrongPass123!"}
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestProtectedEndpoints:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()

    def test_access_profile_without_token(self):
        url = reverse('auth-me')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_profile_with_valid_token(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('auth-me')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == self.user.email

    def test_update_profile(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('auth-me')
        data = {"first_name": "Updated", "last_name": "Name"}
        response = self.client.patch(url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == "Updated"
        assert response.data['last_name'] == "Name"


@pytest.mark.django_db
class TestLogout:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory(email="logout@test.com", password="StrongPass123!")

    def test_logout(self):
        # Login first
        login_url = reverse('auth-login')
        response = self.client.post(login_url, {
            "email": "logout@test.com",
            "password": "StrongPass123!"
        }, format='json')
        refresh_token = response.data['refresh']
        access_token = response.data['access']

        # Logout
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_url = reverse('auth-logout')
        response = self.client.post(logout_url, {"refresh": refresh_token}, format='json')
        assert response.status_code == status.HTTP_200_OK
