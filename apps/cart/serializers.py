from rest_framework import serializers
from decimal import Decimal
from .models import Cart, CartItem
from apps.catalog.serializers import InventorySerializer

class CartItemSerializer(serializers.ModelSerializer):
    item_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    inventory_details = InventorySerializer(source='inventory', read_only=True)
    product_name = serializers.CharField(source='inventory.product.name', read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'inventory', 'inventory_details', 'product_name', 'quantity', 'item_total']
        read_only_fields = ['id']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    cart_total = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    total_after_discount = serializers.SerializerMethodField()
    coupon_code = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'cart_total', 'discount_amount', 'total_after_discount', 'coupon_code', 'updated_at']
        read_only_fields = ['id', 'user', 'updated_at']

    def get_cart_total(self, obj):
        return sum(item.item_total for item in obj.items.all())

    def get_discount_amount(self, obj):
        if not obj.coupon:
            return Decimal('0.00')
        scoped = sum(
            item.item_total for item in obj.items.all()
            if obj.coupon.applies_to(item.inventory.product)
        )
        if scoped <= 0:
            return Decimal('0.00')
        return obj.coupon.discount_for(scoped)

    def get_total_after_discount(self, obj):
        return self.get_cart_total(obj) - self.get_discount_amount(obj)

    def get_coupon_code(self, obj):
        return obj.coupon.code if obj.coupon else None

class CartMergeSerializer(serializers.Serializer):
    session_cart_id = serializers.UUIDField(required=True)
