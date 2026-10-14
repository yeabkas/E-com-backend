from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.orders.models import Order
from apps.payments.provider import get_provider


@pytest.mark.django_db
class TestChapaWebhook:
    def setup_method(self):
        self.client = APIClient()
        self.user_email = 'buyer@example.com'
        from apps.users.models import User
        self.user = User.objects.create_user(
            email=self.user_email, password='x', first_name='B', last_name='U'
        )
        self.order = Order.objects.create(
            user=self.user, status=Order.OrderStatus.PENDING, chapa_tx_ref='gash_abc123'
        )

    def test_webhook_marks_order_paid_when_verified(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={'ok': True, 'raw': {'status': 'success'}}):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'gash_abc123'}, format='json'
            )
        assert resp.status_code == 200
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PAID

    def test_webhook_does_not_mark_paid_when_not_verified(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={'ok': False, 'raw': {}}):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'gash_abc123'}, format='json'
            )
        assert resp.status_code == 200
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PENDING

    def test_webhook_unknown_tx_ref(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={'ok': True, 'raw': {}}):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'nope'}, format='json'
            )
        assert resp.status_code == 404
