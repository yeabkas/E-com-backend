import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.catalog.models import Category, CategoryChangeRequest
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.users.models import User
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestCategoryPublicAPI:

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('category-list')

    def test_list_categories_as_tree(self):
        electronics = CategoryFactory(name="Electronics", slug="electronics", approval_status='APPROVED')
        CategoryFactory(name="Laptops", slug="laptops", parent=electronics, approval_status='APPROVED')
        CategoryFactory(name="Phones", slug="phones", parent=electronics, approval_status='APPROVED')
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

        results = response.data
        assert len(results) == 1
        assert results[0]['name'] == "Electronics"
        assert len(results[0]['subcategories']) == 2

    def test_only_active_categories_shown(self):
        CategoryFactory(is_active=True, approval_status='APPROVED')
        CategoryFactory(is_active=False, approval_status='APPROVED')
        response = self.client.get(self.url)
        results = response.data
        assert len(results) == 1

    def test_pending_and_rejected_categories_excluded_from_public_list(self):
        CategoryFactory(name="Approved Cat", is_active=True, approval_status='APPROVED')
        CategoryFactory(name="Pending Cat", is_active=True, approval_status='PENDING')
        CategoryFactory(name="Rejected Cat", is_active=True, approval_status='REJECTED')

        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        names = [c['name'] for c in response.data]
        assert "Approved Cat" in names
        assert "Pending Cat" not in names
        assert "Rejected Cat" not in names


@pytest.mark.django_db
class TestCategoryApprovalWorkflow:

    def setup_method(self):
        self.client = APIClient()
        self.admin = UserFactory(role=User.Role.ADMIN)
        self.seller = UserFactory(role=User.Role.SELLER)
        self.other_seller = UserFactory(role=User.Role.SELLER)
        self.admin_cat_url = reverse('admin-category-list')

    def test_seller_create_category_defaults_to_pending(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(self.admin_cat_url, {'name': 'Artisan Shoes'}, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        cat = Category.objects.get(id=response.data['id'])
        assert cat.name == 'Artisan Shoes'
        assert cat.approval_status == 'PENDING'
        assert cat.owner == self.seller

        # Verify not visible on public category list
        public_resp = self.client.get(reverse('category-list'))
        assert not any(c['name'] == 'Artisan Shoes' for c in public_resp.data)

    def test_admin_create_category_defaults_to_approved(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.admin_cat_url, {'name': 'Global Fashion'}, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        cat = Category.objects.get(id=response.data['id'])
        assert cat.name == 'Global Fashion'
        assert cat.approval_status == 'APPROVED'

        # Verify immediately visible on public category list
        public_resp = self.client.get(reverse('category-list'))
        assert any(c['name'] == 'Global Fashion' for c in public_resp.data)

    def test_admin_category_list_queryset_scoping(self):
        approved = CategoryFactory(name="Shared Approved", approval_status='APPROVED')
        seller_pending = CategoryFactory(name="Seller Pending", approval_status='PENDING', owner=self.seller)
        other_pending = CategoryFactory(name="Other Pending", approval_status='PENDING', owner=self.other_seller)

        # Seller view
        self.client.force_authenticate(user=self.seller)
        resp = self.client.get(self.admin_cat_url)
        assert resp.status_code == status.HTTP_200_OK
        names = [c['name'] for c in resp.data]
        assert "Shared Approved" in names
        assert "Seller Pending" in names
        assert "Other Pending" not in names

        # Admin view
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(self.admin_cat_url)
        assert resp.status_code == status.HTTP_200_OK
        admin_names = [c['name'] for c in resp.data]
        assert "Shared Approved" in admin_names
        assert "Seller Pending" in admin_names
        assert "Other Pending" in admin_names

    def test_admin_can_approve_pending_category(self):
        pending_cat = CategoryFactory(name="Handmade Rugs", approval_status='PENDING', owner=self.seller)

        self.client.force_authenticate(user=self.admin)
        approve_url = reverse('category-approve', kwargs={'pk': pending_cat.id})
        response = self.client.post(approve_url)
        assert response.status_code == status.HTTP_200_OK

        pending_cat.refresh_from_db()
        assert pending_cat.approval_status == 'APPROVED'
        assert pending_cat.rejection_reason == ''

    def test_admin_can_reject_pending_category_with_reason(self):
        pending_cat = CategoryFactory(name="Duplicate Electronics", approval_status='PENDING', owner=self.seller)

        self.client.force_authenticate(user=self.admin)
        approve_url = reverse('category-approve', kwargs={'pk': pending_cat.id})
        response = self.client.delete(approve_url, {'reason': 'Category already exists as Electronics'}, format='json')
        assert response.status_code == status.HTTP_200_OK

        pending_cat.refresh_from_db()
        assert pending_cat.approval_status == 'REJECTED'
        assert pending_cat.rejection_reason == 'Category already exists as Electronics'

    def test_seller_cannot_approve_or_reject_category(self):
        cat = CategoryFactory(approval_status='PENDING', owner=self.other_seller)
        approve_url = reverse('category-approve', kwargs={'pk': cat.id})

        self.client.force_authenticate(user=self.seller)
        resp_post = self.client.post(approve_url)
        assert resp_post.status_code == status.HTTP_403_FORBIDDEN

        resp_del = self.client.delete(approve_url, {'reason': 'Hacking'}, format='json')
        assert resp_del.status_code == status.HTTP_403_FORBIDDEN

    def test_seller_editing_approved_category_creates_change_request(self):
        shared_cat = CategoryFactory(name="Original Apparel", approval_status='APPROVED')

        self.client.force_authenticate(user=self.seller)
        detail_url = reverse('admin-category-detail', kwargs={'pk': shared_cat.id})
        response = self.client.patch(detail_url, {'name': 'Proposed Apparel'}, format='json')
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert 'change_request_id' in response.data

        # Category is unchanged
        shared_cat.refresh_from_db()
        assert shared_cat.name == 'Original Apparel'

        # Change request exists
        cr = CategoryChangeRequest.objects.get(id=response.data['change_request_id'])
        assert cr.change_type == 'EDIT'
        assert cr.status == 'PENDING'
        assert cr.proposed_changes == {'name': 'Proposed Apparel'}
        assert cr.requested_by == self.seller

    def test_seller_deleting_approved_category_creates_change_request(self):
        shared_cat = CategoryFactory(name="Summer Gear", approval_status='APPROVED')

        self.client.force_authenticate(user=self.seller)
        detail_url = reverse('admin-category-detail', kwargs={'pk': shared_cat.id})
        response = self.client.delete(detail_url)
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Category still exists
        assert Category.objects.filter(id=shared_cat.id).exists()

        cr = CategoryChangeRequest.objects.filter(category=shared_cat, change_type='DELETE').first()
        assert cr is not None
        assert cr.status == 'PENDING'

    def test_admin_approves_edit_change_request(self):
        cat = CategoryFactory(name="Old Name", approval_status='APPROVED')
        cr = CategoryChangeRequest.objects.create(
            category=cat,
            requested_by=self.seller,
            change_type='EDIT',
            proposed_changes={'name': 'New Valid Name'},
            status='PENDING'
        )

        self.client.force_authenticate(user=self.admin)
        cr_approve_url = reverse('change-request-approve', kwargs={'pk': cr.id})
        response = self.client.post(cr_approve_url)
        assert response.status_code == status.HTTP_200_OK

        cr.refresh_from_db()
        assert cr.status == 'APPROVED'
        cat.refresh_from_db()
        assert cat.name == 'New Valid Name'

    def test_admin_approves_delete_change_request_with_products_marks_inactive(self):
        cat = CategoryFactory(name="Active Shoes", approval_status='APPROVED', is_active=True)
        ProductFactory(category=cat)  # Has products
        cr = CategoryChangeRequest.objects.create(
            category=cat,
            requested_by=self.seller,
            change_type='DELETE',
            status='PENDING'
        )

        self.client.force_authenticate(user=self.admin)
        cr_approve_url = reverse('change-request-approve', kwargs={'pk': cr.id})
        response = self.client.post(cr_approve_url)
        assert response.status_code == status.HTTP_200_OK

        cr.refresh_from_db()
        assert cr.status == 'APPROVED'
        cat.refresh_from_db()
        assert cat.is_active is False

    def test_admin_approves_delete_change_request_without_products_deletes_category(self):
        cat = CategoryFactory(name="Empty Category", approval_status='APPROVED')
        cr = CategoryChangeRequest.objects.create(
            category=cat,
            requested_by=self.seller,
            change_type='DELETE',
            status='PENDING'
        )

        self.client.force_authenticate(user=self.admin)
        cr_approve_url = reverse('change-request-approve', kwargs={'pk': cr.id})
        response = self.client.post(cr_approve_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'approved'

        # Category is deleted
        assert not Category.objects.filter(id=cat.id).exists()

    def test_admin_rejects_change_request_with_reason(self):
        cat = CategoryFactory(name="Permanent Name", approval_status='APPROVED')
        cr = CategoryChangeRequest.objects.create(
            category=cat,
            requested_by=self.seller,
            change_type='EDIT',
            proposed_changes={'name': 'Spam Name'},
            status='PENDING'
        )

        self.client.force_authenticate(user=self.admin)
        cr_approve_url = reverse('change-request-approve', kwargs={'pk': cr.id})
        response = self.client.delete(cr_approve_url, {'reason': 'Misleading title'}, format='json')
        assert response.status_code == status.HTTP_200_OK

        cr.refresh_from_db()
        assert cr.status == 'REJECTED'
        assert cr.rejection_reason == 'Misleading title'

        cat.refresh_from_db()
        assert cat.name == 'Permanent Name'
