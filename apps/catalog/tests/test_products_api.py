import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.catalog.tests.factories import ProductFactory, CategoryFactory, InventoryFactory
from apps.users.tests.factories import UserFactory

@pytest.mark.django_db
class TestProductListAPI:

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('product-list')

    def test_list_only_active_products(self):
        ProductFactory(is_active=True)
        ProductFactory(is_active=True)
        ProductFactory(is_active=False)  # Draft, should not appear
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2

    def test_filter_by_category(self):
        electronics = CategoryFactory(name="Electronics", slug="electronics")
        books = CategoryFactory(name="Books", slug="books")
        ProductFactory(category=electronics, is_active=True)
        ProductFactory(category=electronics, is_active=True)
        ProductFactory(category=books, is_active=True)
        response = self.client.get(self.url, {'category': 'electronics'})
        assert response.data['count'] == 2

    def test_filter_by_price_range(self):
        ProductFactory(base_price=25.00, is_active=True)
        ProductFactory(base_price=75.00, is_active=True)
        ProductFactory(base_price=150.00, is_active=True)
        response = self.client.get(self.url, {'min_price': 50, 'max_price': 100})
        assert response.data['count'] == 1

    def test_search_by_keyword(self):
        ProductFactory(name="Red Running Shoes", is_active=True)
        ProductFactory(name="Blue Backpack", is_active=True)
        response = self.client.get(self.url, {'search': 'running shoes'})
        assert response.data['count'] == 1
        assert 'Running Shoes' in response.data['results'][0]['name']

    def test_ordering_by_price_descending(self):
        ProductFactory(name="Cheap", base_price=10.00, is_active=True)
        ProductFactory(name="Expensive", base_price=500.00, is_active=True)
        response = self.client.get(self.url, {'ordering': '-base_price'})
        assert response.data['results'][0]['name'] == "Expensive"


@pytest.mark.django_db
class TestProductDetailAPI:

    def setup_method(self):
        self.client = APIClient()

    def test_get_product_by_slug(self):
        product = ProductFactory(name="Test Product", slug="test-product", is_active=True)
        InventoryFactory(product=product, sku="TP-001", quantity_available=50)
        url = reverse('product-detail', kwargs={'slug': 'test-product'})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == "Test Product"
        assert len(response.data['variants']) == 1

    def test_inactive_product_returns_404_for_customer(self):
        ProductFactory(slug="draft-product", is_active=False)
        url = reverse('product-detail', kwargs={'slug': 'draft-product'})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_inactive_product_returns_200_for_admin(self):
        ProductFactory(slug="draft-product", is_active=False)
        admin = UserFactory(role='ADMIN', is_staff=True, is_superuser=True)
        self.client.force_authenticate(user=admin)
        url = reverse('product-detail', kwargs={'slug': 'draft-product'})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestProductAdmin:

    def setup_method(self):
        self.client = APIClient()
        self.admin = UserFactory(role='ADMIN', is_staff=True, is_superuser=True)
        
    def test_admin_can_create_product(self):
        self.client.force_login(user=self.admin)
        # Note: the admin interface is usually tested differently, 
        # but we can test access to the admin url.
        url = reverse('admin:catalog_product_add')
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_non_admin_cannot_access_product_admin(self):
        customer = UserFactory(role='CUSTOMER')
        self.client.force_login(user=customer)
        url = reverse('admin:catalog_product_add')
        response = self.client.get(url)
        # Admin redirects to login for non-staff
        assert response.status_code == status.HTTP_302_FOUND
