"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/catalog/', include('apps.catalog.urls')),
    path('api/v1/cart/', include('apps.cart.urls')),
    path('api/v1/orders/', include('apps.orders.urls')),
    path('api/v1/reviews/', include('apps.reviews.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/promotions/', include('apps.promotions.urls')),
    path('api/v1/wishlist/', include('apps.wishlist.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
