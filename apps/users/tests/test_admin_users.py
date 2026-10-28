import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.models import User
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestAdminUserManagement:
    def setup_method(self):
        self.client = APIClient()
        self.admin = UserFactory(role=User.Role.ADMIN)
        self.customer = UserFactory(role=User.Role.CUSTOMER)
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_list_and_search_users(self):
        response = self.client.get(reverse('admin-user-list'))
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] >= 2

        response = self.client.get(reverse('admin-user-list'), {'search': self.customer.email})
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['results'][0]['email'] == self.customer.email

    def test_admin_can_update_role_and_suspension(self):
        response = self.client.patch(
            reverse('admin-user-detail', kwargs={'pk': self.customer.pk}),
            {'role': User.Role.SELLER, 'is_suspended': True, 'is_verified': True},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        self.customer.refresh_from_db()
        assert self.customer.role == User.Role.SELLER
        assert self.customer.is_suspended is True
        assert self.customer.is_verified is True

    def test_non_admin_cannot_manage_users(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(reverse('admin-user-list'))
        assert response.status_code == status.HTTP_403_FORBIDDEN
