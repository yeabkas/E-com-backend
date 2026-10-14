import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.users.tests.factories import UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.reviews.models import Review

@pytest.mark.django_db
class TestReviewAPI:

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.product = ProductFactory(average_rating=0.0, review_count=0)

    def test_authenticated_user_can_create_review(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('review-list')
        data = {
            'product': self.product.id,
            'rating': 5,
            'comment': 'Great product!'
        }
        response = self.client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['rating'] == 5
        
        # Verify signal updated product stats
        self.product.refresh_from_db()
        assert self.product.review_count == 1
        assert float(self.product.average_rating) == 5.0

    def test_unauthenticated_cannot_create_review(self):
        url = reverse('review-list')
        data = {
            'product': self.product.id,
            'rating': 4,
            'comment': 'Nice'
        }
        response = self.client.post(url, data, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cannot_review_same_product_twice(self):
        self.client.force_authenticate(user=self.user)
        Review.objects.create(user=self.user, product=self.product, rating=4)
        
        url = reverse('review-list')
        data = {
            'product': self.product.id,
            'rating': 5,
            'comment': 'Changed my mind!'
        }
        response = self.client.post(url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_signal_aggregates_multiple_reviews(self):
        user2 = UserFactory()
        
        Review.objects.create(user=self.user, product=self.product, rating=4)
        Review.objects.create(user=user2, product=self.product, rating=2)
        
        self.product.refresh_from_db()
        assert self.product.review_count == 2
        assert float(self.product.average_rating) == 3.0

    def test_unapproved_reviews_are_hidden(self):
        Review.objects.create(user=self.user, product=self.product, rating=4, is_approved=False)
        
        url = reverse('review-list')
        response = self.client.get(url)
        assert len(response.data['results']) == 0
