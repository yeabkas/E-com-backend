import os
import shutil
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.catalog.models import Product, ProductImage
from django.core.files import File

# Image paths
image_dir = Path(r"C:\Users\yeabk\.gemini\antigravity-ide\brain\0838d254-963c-4265-95e8-44809f86d8d4")
images = {
    'headphones': image_dir / 'product_headphones_1791029092473.jpg',
    'laptop': image_dir / 'product_laptop_1791029109616.jpg',
    'smartphone': image_dir / 'product_smartphone_1791029122814.jpg',
    'jacket': image_dir / 'product_jacket_1791029136640.jpg'
}

print("Assigning mock images to products...")

products = list(Product.objects.all())

if not products:
    print("No products found! Run `python manage.py seed_db` first.")
    exit(1)

# Ensure images exist
for name, path in images.items():
    if not path.exists():
        print(f"Warning: Image not found at {path}")

# Assign images to products based on category, or randomly if not matching
for i, product in enumerate(products):
    # Skip if already has image
    if product.images.exists():
        continue
        
    cat_slug = product.category.slug.lower()
    
    if 'laptop' in cat_slug:
        img_key = 'laptop'
    elif 'smartphone' in cat_slug:
        img_key = 'smartphone'
    elif 'electronic' in cat_slug:
        img_key = 'headphones'
    elif 'clothing' in cat_slug or 'apparel' in cat_slug:
        img_key = 'jacket'
    else:
        # Default to a random image based on index
        keys = list(images.keys())
        img_key = keys[i % len(keys)]
        
    img_path = images[img_key]
    
    if img_path.exists():
        with open(img_path, 'rb') as f:
            django_file = File(f, name=f"{img_key}.jpg")
            ProductImage.objects.create(
                product=product,
                image=django_file,
                alt_text=f"{product.name} image",
                is_primary=True
            )
        print(f"Assigned {img_key}.jpg to {product.name}")

print("Done assigning images!")
