import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.catalog.models import Inventory, Product
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
class TestCsvInventoryImport:
    def setup_method(self):
        self.client = APIClient()
        self.admin = UserFactory(role='ADMIN')
        self.client.force_authenticate(user=self.admin)
        self.category = CategoryFactory(name='Electronics', slug='electronics')
        self.product = ProductFactory(
            name='Existing Product', slug='existing-product', category=self.category
        )
        InventoryFactory(product=self.product, sku='EXIST-1', quantity_available=1)

    def test_import_creates_products_variants_and_updates_inventory(self):
        csv_content = (
            'name,category,description,price,sku,quantity,variant,low_stock_threshold\n'
            'Imported Speaker,Electronics,Great sound,12.50,IMP-1,7,Black,3\n'
        )
        upload = SimpleUploadedFile('products.csv', csv_content.encode(), content_type='text/csv')
        response = self.client.post(
            reverse('admin-product-import'), {'file': upload}, format='multipart'
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data['created'] == 1
        assert response.data['inventory_created'] == 1
        assert Product.objects.filter(slug='imported-speaker').exists()
        inventory = Inventory.objects.get(sku='IMP-1')
        assert inventory.quantity_available == 7
        assert inventory.low_stock_threshold == 3

        update_upload = SimpleUploadedFile(
            'inventory.csv',
            b'product_slug,sku,quantity,variant,low_stock_threshold\n'
            b'existing-product,EXIST-1,9,Default,2\n',
            content_type='text/csv',
        )
        response = self.client.post(
            reverse('admin-product-import'), {'file': update_upload}, format='multipart'
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data['inventory_updated'] == 1
        inventory = Inventory.objects.get(sku='EXIST-1')
        assert inventory.quantity_available == 9
        assert inventory.low_stock_threshold == 2
        assert not response.data['errors']

    def test_failed_row_rolls_back_and_is_not_counted(self):
        csv_content = (
            'name,category,description,price,sku,quantity,variant\n'
            'Collision Product,Electronics,Duplicate SKU,5.00,EXIST-1,5,Default\n'
        )
        upload = SimpleUploadedFile('products.csv', csv_content.encode(), content_type='text/csv')
        response = self.client.post(
            reverse('admin-product-import'), {'file': upload}, format='multipart'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['created'] == 0
        assert response.data['inventory_created'] == 0
        assert len(response.data['errors']) == 1
        assert 'another product' in response.data['errors'][0]['error']
        assert not Product.objects.filter(slug='collision-product').exists()

    def test_inventory_only_row_requires_quantity(self):
        csv_content = 'product_slug,sku,variant\nexisting-product,EXIST-1,Default\n'
        upload = SimpleUploadedFile('inventory.csv', csv_content.encode(), content_type='text/csv')
        response = self.client.post(
            reverse('admin-product-import'), {'file': upload}, format='multipart'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['inventory_updated'] == 0
        assert 'quantity is required' in response.data['errors'][0]['error']


@pytest.mark.django_db
class TestCatalogAdminPermissions:
    def setup_method(self):
        self.client = APIClient()
        self.category = CategoryFactory(name='Security', slug='security')
        self.seller = UserFactory(role='SELLER')
        self.other_seller = UserFactory(role='SELLER')
        self.own_product = ProductFactory(seller=self.seller, category=self.category)
        self.other_product = ProductFactory(seller=self.other_seller, category=self.category)

    def test_anonymous_cannot_use_admin_product_api(self):
        response = self.client.get(reverse('admin-product-list'))
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_use_admin_inventory_api(self):
        customer = UserFactory(role='CUSTOMER')
        self.client.force_authenticate(user=customer)
        response = self.client.get(reverse('admin-inventory-list'))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_seller_only_sees_own_products(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.get(reverse('admin-product-list'))
        assert response.status_code == status.HTTP_200_OK
        ids = {row['id'] for row in response.data['results']}
        assert str(self.own_product.id) in ids
        assert str(self.other_product.id) not in ids

    def test_seller_cannot_edit_shared_category(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.patch(
            reverse('admin-category-detail', kwargs={'pk': self.category.pk}),
            {'name': 'Hijacked Taxonomy'},
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        self.category.refresh_from_db()
        assert self.category.name == 'Security'

    def test_seller_cannot_update_another_sellers_product(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.patch(
            reverse('admin-product-detail', kwargs={'pk': self.other_product.pk}),
            {'name': 'Hijacked'},
            format='json',
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        self.other_product.refresh_from_db()
        assert self.other_product.name != 'Hijacked'

    def test_seller_cannot_add_inventory_to_another_product(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            reverse('admin-inventory-list'),
            {'product': str(self.other_product.id), 'sku': 'OTHER-SKU', 'quantity_available': 5},
            format='json',
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Inventory.objects.filter(sku='OTHER-SKU').exists()


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
