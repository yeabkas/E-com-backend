import uuid
from decimal import Decimal
from django.db import models
from django.db.models.functions import Greatest
from django.conf import settings
from apps.users.models import Address


class Order(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        PROCESSING = 'PROCESSING', 'Processing'
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    
    # Snapshot of the shipping address at checkout
    shipping_address = models.ForeignKey(Address, on_delete=models.PROTECT, null=True, blank=True)
    shipping_name = models.CharField(max_length=255, blank=True)
    shipping_street_line_1 = models.CharField(max_length=255, blank=True)
    shipping_street_line_2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state_province = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_country_code = models.CharField(max_length=2, blank=True)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    
    # Totals
    currency = models.CharField(max_length=3, default='ETB')
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    shipping_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    coupon_code = models.CharField(max_length=50, blank=True)
    discount_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    # Stripe or Payment Gateway ID
    payment_intent_id = models.CharField(max_length=255, blank=True)
    chapa_tx_ref = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    shipping_method_name = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.id} - {self.user.email}"

    def transition_to(self, new_status):
        """Enforce the allowed state machine and keep stock/sales/coupon data consistent."""
        transitions = {
            self.OrderStatus.PENDING: {self.OrderStatus.PAID, self.OrderStatus.CANCELLED},
            self.OrderStatus.PAID: {self.OrderStatus.PROCESSING, self.OrderStatus.SHIPPED, self.OrderStatus.CANCELLED},
            self.OrderStatus.PROCESSING: {self.OrderStatus.SHIPPED, self.OrderStatus.CANCELLED},
            self.OrderStatus.SHIPPED: {self.OrderStatus.DELIVERED},
            self.OrderStatus.DELIVERED: {self.OrderStatus.COMPLETED},
            self.OrderStatus.COMPLETED: set(),
            self.OrderStatus.CANCELLED: set(),
        }
        if new_status not in transitions.get(self.status, set()):
            raise ValueError(f'Invalid transition from {self.status} to {new_status}')

        from apps.catalog.models import Product, Inventory
        previous_status = self.status

        if new_status == self.OrderStatus.PAID:
            for item in self.items.all():
                if item.product_id:
                    Product.objects.filter(id=item.product_id).update(
                        sales_count=models.F('sales_count') + item.quantity
                    )
        elif new_status == self.OrderStatus.CANCELLED:
            # Release stock that was reserved at checkout, including paid orders
            # cancelled by an admin before shipment.
            for item in self.items.all():
                inv = Inventory.objects.filter(sku=item.sku).first()
                if inv is not None:
                    inv.quantity_available += item.quantity
                    inv.quantity_reserved = max(inv.quantity_reserved - item.quantity, 0)
                    inv.save(update_fields=['quantity_available', 'quantity_reserved'])
                if previous_status in (self.OrderStatus.PAID, self.OrderStatus.PROCESSING) and item.product_id:
                    Product.objects.filter(id=item.product_id).update(
                        sales_count=Greatest(
                            models.F('sales_count') - item.quantity,
                            models.Value(0),
                        )
                    )
            # A failed/abandoned order must not consume coupon usage limits.
            from apps.promotions.models import CouponUsage
            CouponUsage.objects.filter(order=self).delete()

        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])
        OrderStatusHistory.objects.create(order=self, status=new_status)

    @property
    def order_number(self):
        return str(self.id).split('-')[0].upper()

    def populate_shipping_snapshot(self, address):
        """Populates the denormalized address fields based on an Address instance."""
        if address:
            self.shipping_address = address
            self.shipping_name = self.user.full_name
            self.shipping_street_line_1 = address.street_line_1
            self.shipping_street_line_2 = address.street_line_2
            self.shipping_city = address.city
            self.shipping_state_province = address.state_province
            self.shipping_postal_code = address.postal_code
            self.shipping_country_code = address.country_code


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    
    # We store the IDs as CharFields so that if the product is deleted, 
    # the historical order item data remains completely intact.
    product_id = models.UUIDField(null=True, blank=True)
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50)
    variant_label = models.CharField(max_length=100, blank=True)
    
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_items'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.quantity} x {self.product_name} in Order {self.order.id}"

    @property
    def total_price(self):
        return self.quantity * self.unit_price


class OrderStatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20, choices=Order.OrderStatus.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_status_history'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.order_id} -> {self.status}'


class ShippingMethod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    free_over_threshold = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'shipping_methods'
        ordering = ['price', 'name']

    def __str__(self):
        return self.name

    def cost_for(self, subtotal: Decimal) -> Decimal:
        if self.free_over_threshold and subtotal >= self.free_over_threshold:
            return Decimal('0.00')
        return self.price
