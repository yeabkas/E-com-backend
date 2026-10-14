import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.tests.factories import UserFactory
from apps.catalog.tests.factories import InventoryFactory

@pytest.mark.django_db
class TestCartAPI:

    def setup_method(self):
        self.client = APIClient()
        self.inventory = InventoryFactory(quantity_available=10)

    def test_anonymous_cart_creation_and_add_item(self):
        url = reverse('cart-add-item')
        data = {'inventory': self.inventory.id, 'quantity': 2}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data['items']) == 1
        assert response.data['items'][0]['quantity'] == 2
        assert float(response.data['cart_total']) == float(self.inventory.product.base_price * 2)

    def test_authenticated_cart_add_item(self):
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        url = reverse('cart-add-item')
        data = {'inventory': self.inventory.id, 'quantity': 1}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['user'] == user.id

    def test_cannot_add_item_with_insufficient_stock(self):
        url = reverse('cart-add-item')
        data = {'inventory': self.inventory.id, 'quantity': 15}
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_update_item_quantity(self):
        # Add item first
        add_url = reverse('cart-add-item')
        add_response = self.client.post(add_url, {'inventory': self.inventory.id, 'quantity': 1}, format='json')
        item_id = add_response.data['items'][0]['id']
        cart_id = add_response.data['id']
        
        # Update quantity
        update_url = reverse('cart-update-item')
        # We need to pass the cart ID for anonymous user
        self.client.credentials(HTTP_X_CART_ID=str(cart_id))
        update_response = self.client.patch(update_url, {'item_id': item_id, 'quantity': 5}, format='json')
        
        assert update_response.status_code == status.HTTP_200_OK
        assert update_response.data['items'][0]['quantity'] == 5

    def test_remove_item(self):
        # Add item first
        add_url = reverse('cart-add-item')
        add_response = self.client.post(add_url, {'inventory': self.inventory.id, 'quantity': 1}, format='json')
        item_id = add_response.data['items'][0]['id']
        cart_id = add_response.data['id']
        
        # Remove item
        remove_url = reverse('cart-remove-item')
        self.client.credentials(HTTP_X_CART_ID=str(cart_id))
        remove_response = self.client.delete(remove_url, {'item_id': item_id}, format='json')
        
        assert remove_response.status_code == status.HTTP_200_OK
        assert len(remove_response.data['items']) == 0

    def test_merge_anonymous_cart_into_authenticated(self):
        # 1. Create anonymous cart and add item
        add_url = reverse('cart-add-item')
        anon_response = self.client.post(add_url, {'inventory': self.inventory.id, 'quantity': 2}, format='json')
        anon_cart_id = anon_response.data['id']
        
        # 2. Authenticate user
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        # 3. Merge
        merge_url = reverse('cart-merge')
        merge_response = self.client.post(merge_url, {'session_cart_id': anon_cart_id}, format='json')
        
        assert merge_response.status_code == status.HTTP_200_OK
        assert len(merge_response.data['items']) == 1
        assert merge_response.data['items'][0]['quantity'] == 2
        assert merge_response.data['user'] == user.id
