import random
from django.core.management.base import BaseCommand
from apps.users.models import User
from apps.users.tests.factories import UserFactory
from apps.catalog.tests.factories import CategoryFactory, ProductFactory, InventoryFactory
from apps.catalog.models import Category, Product

class Command(BaseCommand):
    help = 'Seeds the database with realistic dummy data for local development'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database with dummy data...')

        import uuid

        # 1. Create Admin Users
        for admin_email in ['Admin@login.com', 'admin@login.com', 'test@admin.com', 'admin@example.com']:
            norm_email = admin_email.strip().lower()
            fixed_id = uuid.uuid5(uuid.NAMESPACE_DNS, norm_email)
            user = User.objects.filter(email__iexact=norm_email).first() or User.objects.filter(id=fixed_id).first()
            if user and user.id != fixed_id:
                user.delete()
                user = None

            if not user:
                user = User(
                    id=fixed_id,
                    email=norm_email,
                    first_name='Admin',
                    last_name='User',
                    role=User.Role.ADMIN,
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                    is_verified=True,
                )
                user.set_password('adminpassword123')
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Created admin user: {norm_email} (password: adminpassword123)'))
            else:
                user.set_password('adminpassword123')
                user.role = User.Role.ADMIN
                user.is_superuser = True
                user.is_staff = True
                user.is_active = True
                user.save()
                self.stdout.write(f'Updated admin user {norm_email}.')

        # 1b. Create Demo Seller & Customer
        for u in [
            {'email': 'seller@example.com', 'password': 'sellerpassword123', 'first_name': 'Demo', 'last_name': 'Seller', 'role': User.Role.SELLER, 'is_staff': True, 'is_superuser': False},
            {'email': 'customer@example.com', 'password': 'customerpassword123', 'first_name': 'Demo', 'last_name': 'Customer', 'role': User.Role.CUSTOMER, 'is_staff': False, 'is_superuser': False},
        ]:
            norm_email = u['email'].strip().lower()
            fixed_id = uuid.uuid5(uuid.NAMESPACE_DNS, norm_email)
            demo_user = User.objects.filter(email__iexact=norm_email).first() or User.objects.filter(id=fixed_id).first()
            if demo_user and demo_user.id != fixed_id:
                demo_user.delete()
                demo_user = None

            if not demo_user:
                demo_user = User(
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
                demo_user.set_password(u['password'])
                demo_user.save()
                self.stdout.write(self.style.SUCCESS(f"Created {u['role']} user: {norm_email}"))
            else:
                demo_user.set_password(u['password'])
                demo_user.save()

        # 2. Create Dummy Customers
        customer_count = 5
        if User.objects.filter(role='CUSTOMER').count() < customer_count:
            for _ in range(customer_count):
                UserFactory()
            self.stdout.write(self.style.SUCCESS(f'Created {customer_count} random customers.'))

        # 3. Create Categories
        if not Category.objects.exists():
            electronics = CategoryFactory(name="Electronics", slug="electronics")
            CategoryFactory(name="Laptops", slug="laptops", parent=electronics)
            CategoryFactory(name="Smartphones", slug="smartphones", parent=electronics)
            
            apparel = CategoryFactory(name="Apparel", slug="apparel")
            CategoryFactory(name="Mens Clothing", slug="mens-clothing", parent=apparel)
            CategoryFactory(name="Womens Clothing", slug="womens-clothing", parent=apparel)
            
            CategoryFactory(name="Books", slug="books")
            
            self.stdout.write(self.style.SUCCESS('Created root and nested categories.'))

        # 4. Create Products and Inventory
        if Product.objects.count() < 20:
            categories = list(Category.objects.exclude(parent__isnull=True))
            if not categories:
                categories = list(Category.objects.all())
                
            for _ in range(20):
                category = random.choice(categories)
                product = ProductFactory(
                    category=category,
                    base_price=random.randint(15, 999) + 0.99,
                    average_rating=random.uniform(3.5, 5.0),
                    review_count=random.randint(0, 150)
                )
                
                # Create 1-3 Inventory variants per product
                for i in range(random.randint(1, 3)):
                    InventoryFactory(
                        product=product,
                        variant_label=f"Variant {i+1}",
                        quantity_available=random.randint(10, 200)
                    )
                    
            self.stdout.write(self.style.SUCCESS('Created 20 random products with inventory variants.'))

        self.stdout.write(self.style.SUCCESS('Database seeding complete!'))
