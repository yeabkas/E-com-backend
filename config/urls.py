"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def debug_info(request):
    """Diagnostic endpoint to troubleshoot deployment issues."""
    from django.db import connection
    db_engine = settings.DATABASES['default']['ENGINE']
    db_name = settings.DATABASES['default'].get('NAME', 'unknown')
    session_engine = getattr(settings, 'SESSION_ENGINE', 'default (db)')
    is_vercel = bool(settings.__dict__.get('is_production', False))

    # Check if session is active
    session_key = request.session.session_key if hasattr(request, 'session') else None
    session_user = request.session.get('_auth_user_id') if hasattr(request, 'session') else None

    # Check JWT auth
    jwt_user = None
    if hasattr(request, 'META'):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            jwt_user = 'token-present'

    # Check cookies received
    cookies_received = list(request.COOKIES.keys())

    return JsonResponse({
        'db_engine': db_engine,
        'db_name': str(db_name),
        'session_engine': session_engine,
        'session_cookie_secure': getattr(settings, 'SESSION_COOKIE_SECURE', 'NOT SET'),
        'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', 'NOT SET'),
        'session_cookie_samesite': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'NOT SET'),
        'is_production': is_vercel,
        'session_key': session_key,
        'session_user_id': session_user,
        'jwt_auth': jwt_user,
        'cookies_received': cookies_received,
        'database_url_set': bool(settings.__dict__.get('database_url', None)) or 'DATABASE_URL' in __import__('os').environ,
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/debug/', debug_info),
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

