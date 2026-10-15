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

        # 1. Create Admin Users
        for admin_email in ['Admin@login.com', 'admin@login.com', 'test@admin.com', 'admin@example.com']:
            user = User.objects.filter(email__iexact=admin_email).first()
            if not user:
                User.objects.create_superuser(
                    email=admin_email,
                    password='adminpassword123',
                    first_name='Admin',
                    last_name='User'
                )
                self.stdout.write(self.style.SUCCESS(f'Created admin user: {admin_email} (password: adminpassword123)'))
            else:
                user.set_password('adminpassword123')
                user.role = User.Role.ADMIN
                user.is_superuser = True
                user.is_staff = True
                user.is_active = True
                user.save()
                self.stdout.write(f'Updated admin user {admin_email}.')

        # 1b. Create Demo Seller
        seller_email = 'seller@example.com'
        seller_user = User.objects.filter(email=seller_email).first()
        if not seller_user:
            User.objects.create_user(
                email=seller_email,
                password='sellerpassword123',
                first_name='Demo',
                last_name='Seller',
                role=User.Role.SELLER,
                is_staff=True,
                is_verified=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created demo seller: {seller_email} (password: sellerpassword123)'))

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
