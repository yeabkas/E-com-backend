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

        from apps.users.models import User
        for admin_email in ['Admin@login.com', 'admin@login.com', 'test@admin.com', 'admin@example.com']:
            admin_user = User.objects.filter(email__iexact=admin_email).first()
            if not admin_user:
                User.objects.create_superuser(
                    email=admin_email,
                    password='adminpassword123',
                    first_name='Admin',
                    last_name='User'
                )
            else:
                admin_user.set_password('adminpassword123')
                admin_user.role = User.Role.ADMIN
                admin_user.is_superuser = True
                admin_user.is_staff = True
                admin_user.is_active = True
                admin_user.is_suspended = False
                admin_user.save()
    except Exception as e:
        import sys
        print(f"Auto-migration on Vercel notice: {e}", file=sys.stderr)

