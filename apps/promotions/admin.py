from django.contrib import admin

from .models import Coupon, CouponUsage


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'type', 'value', 'min_order_amount', 'max_uses', 'valid_until', 'is_active', 'created_at']
    list_filter = ['type', 'is_active']
    search_fields = ['code']


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ['coupon', 'user', 'order', 'used_at']
