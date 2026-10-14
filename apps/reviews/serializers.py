from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    verified_purchase = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'product', 'product_slug', 'user', 'user_name', 'rating', 'comment', 'verified_purchase', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_verified_purchase(self, obj):
        from apps.orders.models import Order, OrderItem
        return OrderItem.objects.filter(
            order__user=obj.user,
            order__status__in=[Order.OrderStatus.PAID, Order.OrderStatus.SHIPPED, Order.OrderStatus.DELIVERED, Order.OrderStatus.COMPLETED],
            product_id=obj.product_id,
        ).exists()

    def validate(self, attrs):
        # A user can only have one review per product.
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return attrs

        product = attrs.get('product')
        if not self.instance and Review.objects.filter(user=request.user, product=product).exists():
            raise serializers.ValidationError("You have already reviewed this product.")
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
