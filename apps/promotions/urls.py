from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'admin/coupons', views.AdminCouponViewSet, basename='admin-coupon')
router.register(r'seller/coupons', views.SellerCouponViewSet, basename='seller-coupon')

urlpatterns = [
    path('', include(router.urls)),
]
