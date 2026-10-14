import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.models import Address
from apps.users.tests.factories import UserFactory, AddressFactory


@pytest.mark.django_db
class TestAddressCreate:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('address-list')

    def test_create_address(self):
        data = {
            "label": "Home",
            "street_line_1": "123 Main St",
            "city": "Springfield",
            "state_province": "IL",
            "postal_code": "62704",
            "country_code": "US",
            "is_default": True
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['label'] == "Home"
        assert response.data['is_default'] is True

    def test_max_5_addresses_enforced(self):
        for i in range(5):
            AddressFactory(user=self.user)
        data = {
            "label": "Sixth",
            "street_line_1": "Too Many St",
            "city": "Error",
            "state_province": "XX",
            "postal_code": "00000",
            "country_code": "US",
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAddressList:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('address-list')

    def test_list_only_own_addresses(self):
        AddressFactory(user=self.user)
        AddressFactory(user=self.user)
        other_user = UserFactory()
        AddressFactory(user=other_user)
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2

    def test_unauthenticated_cannot_list_addresses(self):
        client = APIClient()
        response = client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAddressDefault:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('address-list')

    def test_only_one_default_address(self):
        first = AddressFactory(user=self.user, is_default=True)
        data = {
            "label": "Office",
            "street_line_1": "456 Oak Ave",
            "city": "Springfield",
            "state_province": "IL",
            "postal_code": "62704",
            "country_code": "US",
            "is_default": True
        }
        response = self.client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        # Old default should be unset
        first.refresh_from_db()
        assert first.is_default is False
        # New one should be default
        defaults = Address.objects.filter(user=self.user, is_default=True)
        assert defaults.count() == 1
        default_address = defaults.first()
        assert default_address is not None
        assert default_address.label == "Office"


@pytest.mark.django_db
class TestAddressUpdateDelete:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_update_address(self):
        address = AddressFactory(user=self.user, city="OldCity")
        url = reverse('address-detail', kwargs={'pk': str(address.id)})
        response = self.client.patch(url, {"city": "NewCity"}, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['city'] == "NewCity"

    def test_delete_address(self):
        address = AddressFactory(user=self.user)
        url = reverse('address-detail', kwargs={'pk': str(address.id)})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert Address.objects.filter(pk=address.pk).count() == 0

    def test_cannot_update_other_users_address(self):
        other_user = UserFactory()
        address = AddressFactory(user=other_user)
        url = reverse('address-detail', kwargs={'pk': str(address.id)})
        response = self.client.patch(url, {"city": "Hacked"}, format='json')
        assert response.status_code == status.HTTP_404_NOT_FOUND
