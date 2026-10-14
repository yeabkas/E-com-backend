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

        # 1. Create Admin User
        admin_email = 'admin@example.com'
        if not User.objects.filter(email=admin_email).exists():
            User.objects.create_superuser(
                email=admin_email,
                password='adminpassword123',
                first_name='Admin',
                last_name='User'
            )
            self.stdout.write(self.style.SUCCESS(f'Created admin user: {admin_email} (password: adminpassword123)'))
        else:
            self.stdout.write(f'Admin user {admin_email} already exists.')

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
