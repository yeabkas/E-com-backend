import os
import uuid
from abc import ABC, abstractmethod

import requests
from django.conf import settings


class PaymentProvider(ABC):
    @abstractmethod
    def initialize(self, order, callback_url: str, return_url: str | None = None, **kwargs) -> dict: ...

    @abstractmethod
    def verify(self, tx_ref: str) -> dict: ...


class ChapaProvider(PaymentProvider):
    BASE = 'https://api.chapa.co/v1'

    def initialize(self, order, callback_url: str, return_url: str | None = None, **kwargs) -> dict:
        secret = os.environ.get('CHAPA_SECRET_KEY') or getattr(settings, 'CHAPA_SECRET_KEY', '')
        if not secret:
            raise RuntimeError('CHAPA_SECRET_KEY is not configured')

        tx_ref = kwargs.get('tx_ref') or f"gash_{order.id.hex[:12]}"
        payload = {
            'amount': str(order.total_amount),
            'currency': 'ETB',
            'email': order.user.email,
            'first_name': order.user.first_name,
            'last_name': order.user.last_name,
            'tx_ref': tx_ref,
            'callback_url': callback_url,
            'return_url': return_url or callback_url,
            'customization': {'title': 'GASH E-COM Order', 'description': f'Order {order.id}'},
        }
        r = requests.post(
            f'{self.BASE}/transaction/initialize',
            json=payload,
            headers={'Authorization': f'Bearer {secret}'},
            timeout=20,
        )
        data = r.json()
        if r.status_code >= 400 or data.get('status') != 'success':
            raise RuntimeError(f"Chapa init failed: {data}")
        return {'tx_ref': tx_ref, 'checkout_url': data['data']['checkout_url']}

    def verify(self, tx_ref: str) -> dict:
        secret = os.environ.get('CHAPA_SECRET_KEY') or getattr(settings, 'CHAPA_SECRET_KEY', '')
        r = requests.get(
            f'{self.BASE}/transaction/verify/{tx_ref}',
            headers={'Authorization': f'Bearer {secret}'},
            timeout=20,
        )
        data = r.json()
        payload = data.get('data') or {}
        return {
            'ok': r.status_code == 200 and data.get('status') == 'success' and payload.get('status') == 'success',
            'amount': payload.get('amount'),
            'currency': payload.get('currency'),
            'raw': data,
        }


_default_provider: PaymentProvider | None = None


def get_provider() -> PaymentProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = ChapaProvider()
    return _default_provider
