import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from decimal import Decimal
from apps.users.tests.factories import UserFactory, AddressFactory
from apps.catalog.tests.factories import InventoryFactory, ProductFactory
from apps.cart.models import Cart, CartItem
from apps.orders.models import Order

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
        assert float(response.data['total_amount']) == 40.0
        
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
