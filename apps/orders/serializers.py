from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory, ShippingMethod
from apps.users.models import Address

class OrderItemSerializer(serializers.ModelSerializer):
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product_id', 'product_name', 'sku', 'variant_label', 'quantity', 'unit_price', 'total_price']
        read_only_fields = fields

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['status', 'created_at']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    order_number = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user', 'status', 'items', 'status_history', 
            'shipping_name', 'shipping_street_line_1', 'shipping_street_line_2',
            'shipping_city', 'shipping_state_province', 'shipping_postal_code', 'shipping_country_code',
            'currency', 'subtotal', 'tax_amount', 'shipping_amount', 'total_amount', 'shipping_method_name',
            'coupon_code', 'discount_amount',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = '__all__'

class CheckoutSerializer(serializers.Serializer):
    shipping_address_id = serializers.UUIDField(required=True)
    shipping_method_id = serializers.UUIDField(required=False)
    
    def validate_shipping_address_id(self, value):
        user = self.context['request'].user
        try:
            address = Address.objects.get(id=value, user=user)
        except Address.DoesNotExist:
            raise serializers.ValidationError("Invalid shipping address or address does not belong to the user.")
        return address
