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

        import uuid
        from apps.users.models import User

        demo_users = [
            {
                'email': 'admin@login.com',
                'password': 'adminpassword123',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'admin@example.com',
                'password': 'adminpassword123',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'customer@example.com',
                'password': 'customerpassword123',
                'first_name': 'Demo',
                'last_name': 'Customer',
                'role': User.Role.CUSTOMER,
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'email': 'seller@example.com',
                'password': 'sellerpassword123',
                'first_name': 'Demo',
                'last_name': 'Seller',
                'role': User.Role.SELLER,
                'is_staff': True,
                'is_superuser': False,
            },
        ]

        for u in demo_users:
            # pyrefly: ignore [missing-attribute]
            norm_email = u['email'].strip().lower()
            fixed_id = uuid.uuid5(uuid.NAMESPACE_DNS, norm_email)
            user_obj = User.objects.filter(email__iexact=norm_email).first() or User.objects.filter(id=fixed_id).first()

            if not user_obj:
                # Only create if user doesn't exist yet
                user_obj = User(
                    id=fixed_id,
                    email=norm_email,
                    first_name=u['first_name'],
                    last_name=u['last_name'],
                    role=u['role'],
                    is_staff=u['is_staff'],
                    is_superuser=u['is_superuser'],
                    is_active=True,
                    is_verified=True,
                )
                # pyrefly: ignore [bad-argument-type]
                user_obj.set_password(u['password'])
                user_obj.save()
            else:
                # Update role/permissions WITHOUT re-hashing the password.
                # Re-hashing on every cold start changes the password hash
                # (due to random salt), which invalidates Django admin sessions
                # because session_hash is derived from the password hash.
                needs_save = False
                if user_obj.email != norm_email:
                    user_obj.email = norm_email
                    needs_save = True
                if user_obj.role != u['role']:
                    user_obj.role = u['role']
                    needs_save = True
                if user_obj.is_staff != u['is_staff']:
                    user_obj.is_staff = u['is_staff']
                    needs_save = True
                if user_obj.is_superuser != u['is_superuser']:
                    user_obj.is_superuser = u['is_superuser']
                    needs_save = True
                if not user_obj.is_active:
                    user_obj.is_active = True
                    needs_save = True
                if not user_obj.is_verified:
                    user_obj.is_verified = True
                    needs_save = True
                # Only set password if user can't log in with the expected password
                if not user_obj.check_password(u['password']):
                    user_obj.set_password(u['password'])
                    needs_save = True
                if needs_save:
                    user_obj.save()
    except Exception as e:
        import sys
        print(f"Auto-migration on Vercel notice: {e}", file=sys.stderr)

