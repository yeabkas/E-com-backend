"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health_check(request):
    checks = {'database': False, 'cache': False}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks['database'] = True
    except Exception:
        pass
    try:
        cache.set('healthcheck', 'ok', timeout=10)
        checks['cache'] = cache.get('healthcheck') == 'ok'
    except Exception:
        pass
    healthy = all(checks.values())
    return JsonResponse(
        {'status': 'ok' if healthy else 'degraded', 'checks': checks},
        status=200 if healthy else 503,
    )



def debug_info(request):
    """Diagnostic endpoint to troubleshoot deployment and persistence issues."""
    if not settings.DEBUG or not getattr(request.user, 'is_staff', False):
        return JsonResponse({'error': 'Not found'}, status=404)
    from apps.users.models import User
    from apps.catalog.models import Product
    from apps.wishlist.models import WishlistItem

    db_engine = settings.DATABASES['default']['ENGINE']
    db_host = settings.DATABASES['default'].get('HOST', 'unknown')
    db_name = settings.DATABASES['default'].get('NAME', 'unknown')
    session_engine = getattr(settings, 'SESSION_ENGINE', 'default (db)')

    # Check if session is active
    session_key = request.session.session_key if hasattr(request, 'session') else None
    session_user = request.session.get('_auth_user_id') if hasattr(request, 'session') else None

    # Check request user
    is_authenticated = request.user.is_authenticated if hasattr(request, 'user') else False
    user_email = request.user.email if is_authenticated else None

    # Check JWT auth
    jwt_user = None
    if hasattr(request, 'META'):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            jwt_user = 'token-present'

    # Check cookies received
    cookies_received = list(request.COOKIES.keys())

    # Live DB counts
    try:
        users_count = User.objects.count()
        products_count = Product.objects.count()
        wishlist_count = WishlistItem.objects.count()
        db_connected = True
    except Exception as e:
        users_count = str(e)
        products_count = str(e)
        wishlist_count = str(e)
        db_connected = False

    return JsonResponse({
        'db_engine': db_engine,
        'db_host': str(db_host),
        'db_name': str(db_name),
        'db_connected': db_connected,
        'users_count': users_count,
        'products_count': products_count,
        'wishlist_count': wishlist_count,
        'session_engine': session_engine,
        'session_save_every_request': getattr(settings, 'SESSION_SAVE_EVERY_REQUEST', False),
        'session_cookie_secure': getattr(settings, 'SESSION_COOKIE_SECURE', 'NOT SET'),
        'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', 'NOT SET'),
        'session_cookie_samesite': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'NOT SET'),
        'secure_proxy_ssl_header': getattr(settings, 'SECURE_PROXY_SSL_HEADER', None),
        'session_key': session_key,
        'session_user_id': session_user,
        'is_authenticated': is_authenticated,
        'user_email': user_email,
        'jwt_auth': jwt_user,
        'cookies_received': cookies_received,
        'is_secure_request': request.is_secure(),
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/health/', health_check, name='health-check'),
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

