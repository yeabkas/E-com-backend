from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'admin/categories', views.AdminCategoryViewSet, basename='admin-category')
router.register(r'admin/products', views.AdminProductViewSet, basename='admin-product')
router.register(r'admin/inventory', views.AdminInventoryViewSet, basename='admin-inventory')

urlpatterns = [
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('sellers/', views.SellerListView.as_view(), name='seller-list'),
    path('sellers/<uuid:pk>/', views.SellerDetailView.as_view(), name='seller-detail'),
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('restock-subscriptions/', views.RestockSubscriptionCreateView.as_view(), name='restock-sub-create'),
    path('admin/import-products/', views.AdminProductImportView.as_view(), name='admin-product-import'),
    # Category approval workflow
    path('admin/categories/<uuid:pk>/approve/', views.CategoryApprovalView.as_view(), name='category-approve'),
    path('admin/change-requests/', views.ChangeRequestListView.as_view(), name='change-request-list'),
    path('admin/change-requests/<uuid:pk>/approve/', views.ChangeRequestApprovalView.as_view(), name='change-request-approve'),
    path('', include(router.urls)),
]
