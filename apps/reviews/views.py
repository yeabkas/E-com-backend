from rest_framework import viewsets, permissions, filters, throttling
from django_filters.rest_framework import DjangoFilterBackend
from .models import Review
from .serializers import ReviewSerializer


class ReviewThrottle(throttling.ScopedRateThrottle):
    scope = 'reviews'

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user

class ReviewViewSet(viewsets.ModelViewSet):
    """
    API for creating and viewing product reviews.
    Only authenticated users can create/update their own reviews.
    Anyone can list reviews.
    """
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['product__slug', 'rating']
    ordering_fields = ['created_at', 'rating']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsOwnerOrReadOnly()]
        return [permissions.AllowAny()]

    throttle_classes = []

    def get_throttles(self):
        if self.action == 'create':
            return [ReviewThrottle()]
        return []

    def get_queryset(self):
        # Only return approved reviews unless it's the admin
        user = self.request.user
        qs = Review.objects.select_related('user', 'product')
        if user.is_authenticated and getattr(user, 'is_staff', False):
            return qs
        return qs.filter(is_approved=True)
