import pytest
from decimal import Decimal

from rest_framework.test import APIClient

from apps.catalog.models import Product, Inventory, Category
from apps.cart.models import Cart
from apps.promotions.models import Coupon
from apps.users.models import User, Address


@pytest.mark.django_db
class TestCouponFlow:
    def setup_method(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='shopper@example.com', password='x', first_name='S', last_name='M', is_verified=True
        )
        self.cat = Category.objects.create(name='C', slug='c')
        self.product = Product.objects.create(category=self.cat, name='P', slug='p', base_price=Decimal('100.00'))
        self.inv = Inventory.objects.create(product=self.product, sku='SKU1', quantity_available=10)
        self.addr = Address.objects.create(user=self.user, street_line_1='s', city='c', state_province='s', postal_code='1', country_code='ET')
        self.coupon = Coupon.objects.create(code='SAVE10', type='PERCENT', value=Decimal('10'))

    def test_apply_coupon_and_checkout_discount(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post('/api/v1/cart/add_item/', {'inventory': str(self.inv.id), 'quantity': 2}, format='json')
        assert resp.status_code == 201, resp.data
        resp = self.client.post('/api/v1/cart/apply_coupon/', {'code': 'SAVE10'}, format='json')
        assert resp.status_code == 200, resp.data
        assert Decimal(str(resp.data['discount_amount'])) == Decimal('20.00')
        resp = self.client.post('/api/v1/orders/checkout/', {'shipping_address_id': str(self.addr.id)}, format='json')
        assert resp.status_code == 201, resp.data
        assert resp.data['coupon_code'] == 'SAVE10'
        assert Decimal(str(resp.data['discount_amount'])) == Decimal('20.00')
        assert Decimal(str(resp.data['shipping_amount'])) == Decimal('50.00')
        assert Decimal(str(resp.data['total_amount'])) == Decimal('230.00')

    def test_free_shipping_coupon_waives_shipping(self):
        Coupon.objects.create(code='FREESHIP', type='FREE_SHIPPING', value=Decimal('0'))
        self.client.force_authenticate(self.user)
        self.client.post('/api/v1/cart/add_item/', {'inventory': str(self.inv.id), 'quantity': 1}, format='json')
        resp = self.client.post('/api/v1/cart/apply_coupon/', {'code': 'FREESHIP'}, format='json')
        assert resp.status_code == 200, resp.data
        resp = self.client.post('/api/v1/orders/checkout/', {'shipping_address_id': str(self.addr.id)}, format='json')
        assert resp.status_code == 201, resp.data
        assert Decimal(str(resp.data['shipping_amount'])) == Decimal('0.00')
        assert Decimal(str(resp.data['total_amount'])) == Decimal('100.00')

    def test_invalid_coupon_rejected(self):
        self.client.force_authenticate(self.user)
        self.client.post('/api/v1/cart/add_item/', {'inventory': str(self.inv.id), 'quantity': 1}, format='json')
        resp = self.client.post('/api/v1/cart/apply_coupon/', {'code': 'NOPE'}, format='json')
        assert resp.status_code == 404

    def test_min_order_enforced(self):
        self.coupon.min_order_amount = Decimal('500')
        self.coupon.save()
        self.client.force_authenticate(self.user)
        self.client.post('/api/v1/cart/add_item/', {'inventory': str(self.inv.id), 'quantity': 1}, format='json')
        resp = self.client.post('/api/v1/cart/apply_coupon/', {'code': 'SAVE10'}, format='json')
        assert resp.status_code == 400
