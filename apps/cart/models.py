import uuid
from django.db import models
from django.contrib.auth import get_user_model
from apps.catalog.models import Inventory

User = get_user_model()

class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='cart', null=True, blank=True
    )
    coupon = models.ForeignKey('promotions.Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'carts'

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.email}"  # type: ignore
        return f"Anonymous Cart {self.id}"


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cart_items'
        unique_together = ('cart', 'inventory')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.quantity} x {self.inventory.sku} in Cart {self.cart.id}"

    @property
    def item_total(self):
        return self.inventory.product.base_price * self.quantity
