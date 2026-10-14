from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_id', 'product_name', 'sku', 'variant_label', 'quantity', 'unit_price', 'total_price']
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'user__email', 'shipping_name']
    readonly_fields = [
        'subtotal', 'tax_amount', 'shipping_amount', 'total_amount', 
        'shipping_name', 'shipping_street_line_1', 'shipping_street_line_2',
        'shipping_city', 'shipping_state_province', 'shipping_postal_code', 'shipping_country_code'
    ]
    inlines = [OrderItemInline]

    def has_delete_permission(self, request, obj=None):
        return False
