import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestUserRegistration:

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('auth-register')

    def test_register_with_valid_data(self):
        data = {
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "first_name": "John",
            "last_name": "Doe"
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['email'] == "newuser@example.com"
        assert response.data['first_name'] == "John"
        assert 'password' not in response.data
        assert 'password_hash' not in response.data

    def test_register_with_duplicate_email(self):
        data = {
            "email": "existing@example.com",
            "password": "StrongPass123!",
            "first_name": "Jane",
            "last_name": "Doe"
        }
        self.client.post(self.url, data, format='json')
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_with_weak_password(self):
        data = {
            "email": "user@example.com",
            "password": "123",
            "first_name": "John",
            "last_name": "Doe"
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_with_missing_fields(self):
        data = {"email": "user@example.com"}
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_email_is_normalized_to_lowercase(self):
        data = {
            "email": "User@EXAMPLE.com",
            "password": "StrongPass123!",
            "first_name": "Test",
            "last_name": "User"
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['email'] == "user@example.com"
