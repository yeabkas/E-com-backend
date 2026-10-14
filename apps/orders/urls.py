from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrderViewSet, AdminOrderViewSet, ShippingMethodListView, AdminShippingMethodViewSet,
    SellerSalesListView, AdminMetricsView
)

router = DefaultRouter()
router.register(r'admin/orders', AdminOrderViewSet, basename='admin-order')
router.register(r'admin/shipping-methods', AdminShippingMethodViewSet, basename='admin-shipping-method')
router.register(r'', OrderViewSet, basename='order')

urlpatterns = [
    path('shipping-methods/', ShippingMethodListView.as_view(), name='shipping-method-list'),
    path('seller/sales/', SellerSalesListView.as_view(), name='seller-sales'),
    path('admin/metrics/', AdminMetricsView.as_view(), name='admin-metrics'),
    path('', include(router.urls)),
]
