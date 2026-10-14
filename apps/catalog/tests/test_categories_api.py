import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.catalog.tests.factories import CategoryFactory


@pytest.mark.django_db
class TestCategoryAPI:

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('category-list')

    def test_list_categories_as_tree(self):
        electronics = CategoryFactory(name="Electronics", slug="electronics")
        CategoryFactory(name="Laptops", slug="laptops", parent=electronics)
        CategoryFactory(name="Phones", slug="phones", parent=electronics)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        
        # We disabled pagination on categories, so it returns a list directly
        results = response.data
        
        # Only the root category should be in the main list
        assert len(results) == 1
        assert results[0]['name'] == "Electronics"
        # Subcategories should be nested
        assert len(results[0]['subcategories']) == 2

    def test_only_active_categories_shown(self):
        CategoryFactory(is_active=True)
        CategoryFactory(is_active=False)
        response = self.client.get(self.url)
        results = response.data
        assert len(results) == 1
