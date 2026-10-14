from rest_framework import serializers

from .models import Coupon, CouponUsage


class CouponSerializer(serializers.ModelSerializer):
    total_uses = serializers.IntegerField(read_only=True)

    class Meta:
        model = Coupon
        fields = '__all__'

    def validate(self, attrs):
        request = self.context.get('request')
        if request and getattr(request.user, 'role', None) == 'SELLER':
            for p in attrs.get('allowed_products', []) or []:
                if p.seller_id != request.user.id:
                    raise serializers.ValidationError({'allowed_products': 'You can only scope coupons to your own products.'})
        return attrs


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField()
    subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, required=False)
