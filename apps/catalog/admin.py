from django.contrib import admin
from .models import Category, Product, ProductImage, Inventory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class InventoryInline(admin.TabularInline):
    model = Inventory
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'category', 'seller', 'base_price', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [InventoryInline, ProductImageInline]
    readonly_fields = ['average_rating', 'review_count']


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'variant_label', 'quantity_available', 'quantity_reserved']
    list_filter = ['quantity_available']
    search_fields = ['sku', 'product__name']
