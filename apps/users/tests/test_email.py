import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.users.models import User


@pytest.mark.django_db
class TestPasswordReset:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='resetme@example.com', password='OldPass123!', first_name='R', last_name='M'
        )

    def test_password_reset_flow(self):
        resp = self.client.post('/api/v1/auth/password-reset/', {'email': 'resetme@example.com'}, format='json')
        assert resp.status_code == 200
        assert len(mail.outbox) == 1

        from apps.users.tokens import make_reset_token
        token = make_reset_token(self.user.email)
        resp = self.client.post(
            '/api/v1/auth/password-reset-confirm/',
            {'token': token, 'new_password': 'NewPass123!'},
            format='json',
        )
        assert resp.status_code == 200
        resp = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'resetme@example.com', 'password': 'NewPass123!'},
            format='json',
        )
        assert resp.status_code == 200

    def test_reset_with_invalid_token(self):
        resp = self.client.post(
            '/api/v1/auth/password-reset-confirm/',
            {'token': 'bad-token', 'new_password': 'NewPass123!'},
            format='json',
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestVerifyEmail:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='verifyme@example.com', password='x', first_name='V', last_name='M'
        )

    def test_verify_email(self):
        from apps.users.tokens import make_verify_token
        token = make_verify_token(self.user.email)
        resp = self.client.post('/api/v1/auth/verify-email/', {'token': token}, format='json')
        assert resp.status_code == 200
        self.user.refresh_from_db()
        assert self.user.is_verified is True

    def test_checkout_blocked_when_unverified(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/v1/orders/checkout/', {}, format='json')
        assert resp.status_code in (400, 403, 401)
