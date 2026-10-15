"""WSGI config for the E-Commerce platform."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
app = application

if os.environ.get('VERCEL'):
    try:
        from django.core.management import call_command
        call_command('migrate', interactive=False)
        from apps.catalog.models import Category
        if not Category.objects.exists():
            call_command('seed_db')
    except Exception as e:
        import sys
        print(f"Auto-migration on Vercel notice: {e}", file=sys.stderr)

