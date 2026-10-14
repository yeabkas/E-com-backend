import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    class Type(models.TextChoices):
        PERCENT = 'PERCENT', 'Percentage off'
        FIXED = 'FIXED', 'Fixed amount off'
        FREE_SHIPPING = 'FREE_SHIPPING', 'Free shipping'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
    type = models.CharField(max_length=20, choices=Type.choices)
    value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    min_order_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text='Total uses allowed; blank = unlimited')
    per_user_limit = models.PositiveIntegerField(null=True, blank=True, help_text='Uses per customer; blank = unlimited')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_coupons')
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name='seller_coupons',
        help_text='If set, the coupon only discounts this seller\'s products. Null = store-wide (admin).',
    )
    allowed_products = models.ManyToManyField('catalog.Product', blank=True, related_name='coupons', help_text='If empty, applies to all eligible items (store-wide for this seller, or all products for admins). If set, only these products.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coupons'

    def __str__(self):
        return f"{self.code} ({self.type})"

    @property
    def total_uses(self):
        return self.usages.count()

    def is_valid_for(self, subtotal: Decimal, user=None) -> tuple[bool, str]:
        now = timezone.now()
        if not self.is_active:
            return False, 'Coupon is inactive.'
        if self.valid_from and now < self.valid_from:
            return False, 'Coupon not yet valid.'
        if self.valid_until and now > self.valid_until:
            return False, 'Coupon expired.'
        if self.max_uses is not None and self.total_uses >= self.max_uses:
            return False, 'Coupon usage limit reached.'
        if subtotal < self.min_order_amount:
            return False, f'Minimum order amount is {self.min_order_amount}.'
        if user is not None and self.per_user_limit is not None:
            used = self.usages.filter(user=user).count()
            if used >= self.per_user_limit:
                return False, 'You have already used this coupon the maximum number of times.'
        return True, ''

    def applies_to(self, product) -> bool:
        allowed = self.allowed_products.all()
        if allowed.exists():
            return allowed.filter(pk=product.pk).exists()
        if self.seller_id is None:
            return True
        return product.seller_id == self.seller_id

    def discount_for(self, subtotal: Decimal) -> Decimal:
        if self.type == self.Type.PERCENT:
            return (subtotal * self.value / Decimal('100')).quantize(Decimal('0.01'))
        if self.type == self.Type.FIXED:
            return min(self.value, subtotal)
        if self.type == self.Type.FREE_SHIPPING:
            return Decimal('0.00')
        return Decimal('0.00')


class CouponUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usages')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupon_usages')
    order = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='coupon_usage', null=True)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'coupon_usages'
