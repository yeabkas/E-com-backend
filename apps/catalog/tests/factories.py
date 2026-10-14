import factory
from decimal import Decimal
from apps.catalog.models import Product, Category, Inventory, ProductImage

class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    is_active = True

class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    category = factory.SubFactory(CategoryFactory)
    name = factory.Sequence(lambda n: f"Product {n}")
    slug = factory.Sequence(lambda n: f"product-{n}")
    base_price = Decimal("99.99")
    description = factory.Faker("text")
    is_active = True

class InventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Inventory

    product = factory.SubFactory(ProductFactory)
    sku = factory.Sequence(lambda n: f"SKU-{n:04d}")
    variant_label = "Default"
    quantity_available = 100
    quantity_reserved = 0
