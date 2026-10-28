from decimal import Decimal
import hashlib
import hmac
import json
from unittest import mock

import pytest
from django.test import override_settings
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
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '0.00', 'currency': 'ETB', 'raw': {'status': 'success'},
        }):
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

    def test_webhook_does_not_revive_cancelled_order(self):
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.save(update_fields=['status'])
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '0.00', 'currency': 'ETB', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'gash_abc123'}, format='json'
            )
        assert resp.status_code == 200
        assert 'refund' in resp.data['warning'].lower()
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.CANCELLED

    def test_verify_warns_on_late_payment_for_cancelled_order(self):
        self.client.force_authenticate(user=self.user)
        self.order.status = Order.OrderStatus.CANCELLED
        self.order.save(update_fields=['status'])
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '0.00', 'currency': 'ETB', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-verify'), {'order_id': str(self.order.id)}, format='json'
            )
        assert resp.status_code == 409
        assert resp.data['paid'] is True
        assert 'contact support' in resp.data['error'].lower()
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.CANCELLED

    def test_webhook_unknown_tx_ref(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={'ok': True, 'raw': {}}):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'nope'}, format='json'
            )
        assert resp.status_code == 404

    def test_webhook_rejects_amount_mismatch(self):
        self.order.total_amount = Decimal('50.00')
        self.order.save(update_fields=['total_amount'])
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '1.00', 'currency': 'ETB', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'gash_abc123'}, format='json'
            )
        assert resp.status_code == 200
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PENDING

    def test_webhook_rejects_currency_mismatch(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '0.00', 'currency': 'USD', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-webhook'), {'tx_ref': 'gash_abc123'}, format='json'
            )
        assert resp.status_code == 200
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PENDING

    def test_verify_rejects_unknown_reference(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            reverse('chapa-verify'),
            {'order_id': str(self.order.id), 'tx_ref': 'some-other-ref'},
            format='json',
        )
        assert resp.status_code == 400
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PENDING

    def test_verify_marks_order_paid_when_amount_matches(self):
        self.order.total_amount = Decimal('75.00')
        self.order.save(update_fields=['total_amount'])
        provider = get_provider()
        self.client.force_authenticate(user=self.user)
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '75.00', 'currency': 'ETB', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-verify'), {'order_id': str(self.order.id)}, format='json'
            )
        assert resp.status_code == 200
        assert resp.data['paid'] is True
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PAID

    @override_settings(CHAPA_WEBHOOK_SECRET='super-secret')
    def test_webhook_rejects_invalid_signature_when_secret_configured(self):
        provider = get_provider()
        with mock.patch.object(provider, 'verify') as verify:
            resp = self.client.post(
                reverse('chapa-webhook'),
                {'tx_ref': 'gash_abc123'},
                format='json',
                HTTP_X_CHAPA_SIGNATURE='not-valid',
            )
        assert resp.status_code == 401
        verify.assert_not_called()
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PENDING

    @override_settings(CHAPA_WEBHOOK_SECRET='super-secret')
    def test_webhook_accepts_valid_payload_signature(self):
        body = json.dumps({'tx_ref': 'gash_abc123'})
        signature = hmac.new(
            b'super-secret', body.encode('utf-8'), hashlib.sha256
        ).hexdigest()
        provider = get_provider()
        with mock.patch.object(provider, 'verify', return_value={
            'ok': True, 'amount': '0.00', 'currency': 'ETB', 'raw': {},
        }):
            resp = self.client.post(
                reverse('chapa-webhook'),
                data=body,
                content_type='application/json',
                HTTP_X_CHAPA_SIGNATURE=signature,
            )
        assert resp.status_code == 200
        self.order.refresh_from_db()
        assert self.order.status == Order.OrderStatus.PAID

    def test_init_sets_browser_return_url(self):
        self.client.force_authenticate(user=self.user)
        provider = get_provider()
        captured = {}

        def fake_initialize(order, callback_url, return_url=None, **kwargs):
            captured['callback_url'] = callback_url
            captured['return_url'] = return_url
            captured['tx_ref'] = kwargs.get('tx_ref')
            return {'tx_ref': kwargs['tx_ref'], 'checkout_url': 'https://checkout.test/1'}

        with mock.patch.object(provider, 'initialize', side_effect=fake_initialize):
            resp = self.client.post(
                reverse('chapa-init'), {'order_id': str(self.order.id)}, format='json'
            )

        assert resp.status_code == 200
        assert '/checkout/success/' in captured['return_url']
        assert captured['tx_ref'] == self.order.chapa_tx_ref
        assert 'webhooks/chapa' in captured['callback_url']
