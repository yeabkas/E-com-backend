from rest_framework import viewsets, permissions, serializers
from rest_framework.viewsets import ModelViewSet

from apps.users.permissions import IsStoreAdmin

from .models import Coupon, CouponUsage
from .serializers import CouponSerializer


class IsSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'SELLER')


class SellerCouponViewSet(ModelViewSet):
    """CRUD for seller-owned coupons (seller=self)."""
    serializer_class = CouponSerializer
    permission_classes = [IsSeller]

    def get_queryset(self):
        return Coupon.objects.filter(seller=self.request.user)

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, created_by=self.request.user)


class AdminCouponViewSet(ModelViewSet):
    """CRUD for coupons — store admins only."""
    serializer_class = CouponSerializer
    permission_classes = [IsStoreAdmin]
    queryset = Coupon.objects.all()
