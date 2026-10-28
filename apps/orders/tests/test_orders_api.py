import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from decimal import Decimal
from apps.users.tests.factories import UserFactory, AddressFactory
from apps.catalog.tests.factories import InventoryFactory, ProductFactory
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order, OrderItem
from apps.promotions.models import Coupon, CouponUsage

@pytest.mark.django_db
class TestOrderAPI:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.address = AddressFactory(user=self.user)
        self.client.force_authenticate(user=self.user)
        
        # Setup Cart with items
        self.cart = Cart.objects.create(user=self.user)
        self.product1 = ProductFactory(base_price=Decimal('10.00'))
        self.product2 = ProductFactory(base_price=Decimal('20.00'))
        
        self.inventory1 = InventoryFactory(product=self.product1, quantity_available=5)
        self.inventory2 = InventoryFactory(product=self.product2, quantity_available=10)
        
        CartItem.objects.create(cart=self.cart, inventory=self.inventory1, quantity=2) # 2 x $10 = $20
        CartItem.objects.create(cart=self.cart, inventory=self.inventory2, quantity=1) # 1 x $20 = $20
                                                                                       # Total = $40

    def test_checkout_success(self):
        url = reverse('order-checkout')
        data = {'shipping_address_id': self.address.id}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert float(response.data['subtotal']) == 40.0
        # The seeded Standard Delivery method is selected by default (free over 1000).
        assert float(response.data['shipping_amount']) == 50.0
        assert float(response.data['total_amount']) == 90.0
        
        # Verify Inventory decremented
        self.inventory1.refresh_from_db()
        self.inventory2.refresh_from_db()
        assert self.inventory1.quantity_available == 3
        assert self.inventory1.quantity_reserved == 2
        assert self.inventory2.quantity_available == 9
        assert self.inventory2.quantity_reserved == 1
        
        # Verify Cart deleted
        assert not Cart.objects.filter(id=self.cart.id).exists()
        
        # Verify shipping address snapshotted
        order = Order.objects.get(id=response.data['id'])
        assert order.shipping_city == self.address.city

        # Checkout starts the tracking timeline and exposes a friendly order number.
        assert response.data['order_number'] == str(order.id).split('-')[0].upper()
        assert list(order.status_history.values_list('status', flat=True)) == ['PENDING']

    def test_checkout_fails_if_address_invalid(self):
        url = reverse('order-checkout')
        other_user = UserFactory()
        other_address = AddressFactory(user=other_user)
        
        # Cannot checkout with someone else's address
        data = {'shipping_address_id': other_address.id}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_checkout_fails_if_insufficient_stock(self):
        # Update cart to require 10 items of inventory1 (only 5 available)
        CartItem.objects.filter(inventory=self.inventory1).update(quantity=10)
        
        url = reverse('order-checkout')
        data = {'shipping_address_id': self.address.id}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Insufficient stock' in response.data['error']
        
        # Verify cart not deleted
        assert Cart.objects.filter(id=self.cart.id).exists()

    def test_list_past_orders(self):
        # Create an order
        url = reverse('order-checkout')
        self.client.post(url, {'shipping_address_id': self.address.id}, format='json')
        
        list_url = reverse('order-list')
        response = self.client.get(list_url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['status'] == 'PENDING'

    def test_customer_cannot_read_seller_sales(self):
        response = self.client.get(reverse('seller-sales'))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_metrics_include_revenue_series(self):
        admin = UserFactory(role='ADMIN')
        self.client.force_authenticate(user=admin)
        order = Order.objects.create(
            user=self.user,
            status=Order.OrderStatus.PAID,
            subtotal=Decimal('40.00'),
            total_amount=Decimal('85.00'),
        )
        response = self.client.get(reverse('admin-metrics'))
        assert response.status_code == status.HTTP_200_OK
        assert Decimal(str(response.data['revenue'])) == Decimal('85.00')
        assert len(response.data['revenue_by_day']) == 30
        assert sum(float(day['revenue']) for day in response.data['revenue_by_day']) == 85.0

    def test_seller_metrics_are_scoped_and_use_line_item_revenue(self):
        seller = UserFactory(role='SELLER')
        other_seller = UserFactory(role='SELLER')
        own_product = ProductFactory(seller=seller, base_price=Decimal('15.00'))
        other_product = ProductFactory(seller=other_seller, base_price=Decimal('99.00'))
        own_order = Order.objects.create(
            user=self.user,
            status=Order.OrderStatus.PAID,
            subtotal=Decimal('30.00'),
            total_amount=Decimal('30.00'),
        )
        other_order = Order.objects.create(
            user=self.user,
            status=Order.OrderStatus.PAID,
            subtotal=Decimal('99.00'),
            total_amount=Decimal('99.00'),
        )
        OrderItem.objects.create(
            order=own_order, product_id=own_product.id, product_name=own_product.name,
            sku='OWN-1', quantity=2, unit_price=Decimal('15.00'),
        )
        OrderItem.objects.create(
            order=other_order, product_id=other_product.id, product_name=other_product.name,
            sku='OTHER-1', quantity=1, unit_price=Decimal('99.00'),
        )

        self.client.force_authenticate(user=seller)
        response = self.client.get(reverse('admin-metrics'))
        assert response.status_code == status.HTTP_200_OK
        assert Decimal(str(response.data['revenue'])) == Decimal('30.00')
        assert response.data['orders_by_status'] == {'PAID': 1}
        assert sum(float(day['revenue']) for day in response.data['revenue_by_day']) == 30.0

    def _checkout(self):
        response = self.client.post(
            reverse('order-checkout'),
            {'shipping_address_id': self.address.id},
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED
        return Order.objects.get(id=response.data['id'])

    def test_cancelling_pending_order_releases_reserved_stock(self):
        order = self._checkout()
        order.transition_to(Order.OrderStatus.CANCELLED)

        self.inventory1.refresh_from_db()
        self.inventory2.refresh_from_db()
        assert self.inventory1.quantity_available == 5
        assert self.inventory1.quantity_reserved == 0
        assert self.inventory2.quantity_available == 10
        assert self.inventory2.quantity_reserved == 0
        assert list(order.status_history.values_list('status', flat=True)) == [
            'PENDING', 'CANCELLED',
        ]

    def test_cancelling_paid_order_restores_stock_sales_and_coupon(self):
        order = self._checkout()
        coupon = Coupon.objects.create(
            code='CANCEL10', type=Coupon.Type.FIXED, value=Decimal('5.00'),
            created_by=order.user,
        )
        CouponUsage.objects.create(coupon=coupon, user=order.user, order=order)
        order.transition_to(Order.OrderStatus.PAID)

        self.product1.refresh_from_db()
        self.product2.refresh_from_db()
        assert self.product1.sales_count == 2
        assert self.product2.sales_count == 1

        order.transition_to(Order.OrderStatus.PROCESSING)
        order.transition_to(Order.OrderStatus.CANCELLED)

        self.inventory1.refresh_from_db()
        self.inventory2.refresh_from_db()
        self.product1.refresh_from_db()
        self.product2.refresh_from_db()
        assert self.inventory1.quantity_available == 5
        assert self.inventory2.quantity_available == 10
        assert self.product1.sales_count == 0
        assert self.product2.sales_count == 0
        assert not CouponUsage.objects.filter(order=order).exists()
        assert list(order.status_history.values_list('status', flat=True)) == [
            'PENDING', 'PAID', 'PROCESSING', 'CANCELLED',
        ]
