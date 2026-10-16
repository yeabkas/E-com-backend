"""
Django settings for the E-Commerce platform.
Uses SQLite for local development (no Docker required).
"""

import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-key-change-in-production-abc123xyz789'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,.onrender.com,.vercel.app,*').split(',') if h.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'anymail',
    # Local apps
    'apps.users',
    'apps.catalog',
    'apps.cart',
    'apps.orders',
    'apps.reviews',
    'apps.payments',
    'apps.promotions',
    'apps.wishlist',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - PostgreSQL with SQLite Fallback for Local Dev
import sys
import socket

# Email — Console in dev; Anymail (SendGrid) when API key is present
if os.environ.get('ANYMAIL_SENDGRID_API_KEY'):
    EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'
    ANYMAIL = {'SENDGRID_API_KEY': os.environ.get('ANYMAIL_SENDGRID_API_KEY')}
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@gashecom.local')

def is_port_open(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

# Database - Cloud PostgreSQL (Neon), local PostgreSQL (port 5432), or SQLite fallback
NEON_DATABASE_URL = 'postgresql://neondb_owner:npg_lP8Rh3XeGmID@ep-rapid-cake-b4nzwwnn-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require'
database_url = os.environ.get('DATABASE_URL')

# In test mode or when USE_SQLITE is explicitly requested, use SQLite
is_test_runner = 'pytest' in sys.modules or 'test' in sys.argv or bool(os.environ.get('USE_SQLITE'))

if not is_test_runner and not database_url:
    database_url = NEON_DATABASE_URL

if database_url and not is_test_runner:
    try:
        import dj_database_url
        # On serverless (Vercel), conn_max_age MUST be 0 to avoid broken sockets across container freezes
        conn_max_age = 0 if os.environ.get('VERCEL') else 600
        DATABASES = {
            'default': dj_database_url.config(
                default=database_url,
                conn_max_age=conn_max_age,
                conn_health_checks=True,
            )
        }
    except Exception:
        import urllib.parse as up
        up.uses_netloc.append('postgres')
        url = up.urlparse(database_url)
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': url.path[1:],
                'USER': url.username,
                'PASSWORD': url.password,
                'HOST': url.hostname,
                'PORT': url.port or 5432,
                'CONN_MAX_AGE': 0 if os.environ.get('VERCEL') else 600,
            }
        }
elif is_port_open('localhost', 5432) and not is_test_runner:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'ecom_db',
            'USER': 'ecom_user',
            'PASSWORD': 'ecom_password',
            'HOST': 'localhost',
            'PORT': '5432',
        }
    }
else:
    print("Using SQLite database for local development/tests.", file=sys.stderr)
    db_file = BASE_DIR / 'db.sqlite3'
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_file,
        }
    }

# Custom User model
AUTH_USER_MODEL = 'users.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files (uploaded user content)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000/minute',
        'user': '5000/minute',
        'reviews': '10/minute',
        'coupons': '30/minute',
    },
}

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Simple JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# CORS & CSRF
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.environ.get(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173'
    ).split(',') if origin.strip()
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]
CORS_ALLOW_CREDENTIALS = True

# CSRF Trusted Origins (needed for admin actions & secure POST requests from frontend/deployed domains)
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get(
        'CSRF_TRUSTED_ORIGINS',
        'http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,https://*.vercel.app,https://*.onrender.com,https://e-com-backend-delta.vercel.app,https://all-purpose-ecom.vercel.app'
    ).split(',') if origin.strip()
]

# Reverse proxy SSL header — CRITICAL for Vercel & Render
# Tells Django that the request was HTTPS even when forwarded by the edge reverse-proxy over HTTP.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Auth cookie (httpOnly refresh token)
AUTH_REFRESH_COOKIE_NAME = 'refresh_token'
is_production = bool(os.environ.get('VERCEL') or os.environ.get('RENDER'))
AUTH_COOKIE_SECURE = os.environ.get('AUTH_COOKIE_SECURE', 'True' if is_production else 'False').lower() in ('true', '1', 'yes')
AUTH_COOKIE_SAMESITE = os.environ.get('AUTH_COOKIE_SAMESITE', 'None' if is_production else 'Lax')

# Session & CSRF cookie settings — CRITICAL for Django admin on HTTPS/serverless (Vercel)
# Without these, the admin panel gets 403 CSRF errors and loses sessions between clicks.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Explicit: persist sessions in the database, not memory/filesystem
SESSION_SAVE_EVERY_REQUEST = True             # Refresh session in database on each request
SESSION_COOKIE_SECURE = is_production        # Must be True on HTTPS or browser won't send session cookie
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'              # Lax is sufficient for same-domain admin navigation
CSRF_COOKIE_SECURE = is_production           # Must be True on HTTPS or CSRF validation fails
CSRF_COOKIE_SAMESITE = 'Lax'

# Celery / Redis
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CHAPA_SECRET_KEY = os.environ.get('CHAPA_SECRET_KEY', '')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Cache: Redis if configured, otherwise in-memory LocMemCache (for serverless/local dev)
REDIS_URL = os.environ.get('REDIS_URL')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'ecom_cache',
        }
    }

CELERY_BEAT_SCHEDULE = {
    # Hourly sweep: cancel stale unpaid orders, expire abandoned anonymous carts.
    'hourly-order-and-cart-cleanup': {
        'task': 'apps.orders.tasks.expire_unpaid_orders',
        'schedule': 3600.0,
    },
  'low-stock-alerts': {
        'task': 'apps.orders.tasks.send_low_stock_alerts',
        'schedule': 14400.0,
    },
}
