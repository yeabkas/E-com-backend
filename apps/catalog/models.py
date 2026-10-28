import uuid
from decimal import Decimal
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    APPROVAL_CHOICES = [
        ('APPROVED', 'Approved'),
        ('PENDING', 'Pending Approval'),
        ('REJECTED', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories'
    )
    owner = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_categories'
    )
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='APPROVED')
    rejection_reason = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or 'category'
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class CategoryChangeRequest(models.Model):
    """
    Tracks requested changes (edit/delete) to approved categories
    by non-admin users, pending admin approval.
    """
    CHANGE_TYPES = [
        ('EDIT', 'Edit'),
        ('DELETE', 'Delete'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='change_requests')
    requested_by = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='category_change_requests'
    )
    change_type = models.CharField(max_length=10, choices=CHANGE_TYPES)
    # For EDIT: store the proposed changes as JSON
    proposed_changes = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    rejection_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_change_requests'
    )

    class Meta:
        db_table = 'category_change_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.change_type} request for {self.category.name} by {self.requested_by}"


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    seller = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='products'
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)

    # Denormalized fields for future phases (Phase 5)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('0.00'))
    review_count = models.PositiveIntegerField(default=0)
    sales_count = models.PositiveIntegerField(default=0)
    ranking = models.PositiveIntegerField(default=0, db_index=True)

    # Note: SearchVectorField is omitted for SQLite compatibility in local dev.
    # In production with PostgreSQL, we'd add: search_vector = SearchVectorField(null=True)
    # Full-text search is implemented in the view layer via SearchVector when on Postgres.

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/%Y/%m/', null=True, blank=True)
    image_data = models.TextField(blank=True, null=True)
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_images'
        ordering = ['order', '-created_at']

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            # Ensure only one primary image per product
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class Inventory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=50, unique=True)
    variant_label = models.CharField(max_length=100, default='Default')
    quantity_available = models.PositiveIntegerField(default=0)
    quantity_reserved = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    low_stock_alerted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _previous_available = None

    class Meta:
        db_table = 'inventory'
        verbose_name_plural = 'inventories'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._previous_available = self.quantity_available

    def save(self, *args, **kwargs):
        if self.quantity_available > self.low_stock_threshold and self.low_stock_alerted:
            self.low_stock_alerted = False
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'low_stock_alerted'}

        previous = self._previous_available
        super().save(*args, **kwargs)
        self._previous_available = self.quantity_available

        if previous is not None and previous == 0 and self.quantity_available > 0:
            from apps.orders.tasks import send_restock_notifications
            try:
                send_restock_notifications.delay(str(self.product_id))
            except Exception:
                # Email dispatch must never break inventory updates.
                pass

    def __str__(self):
        return f"{self.product.name} - {self.sku} ({self.variant_label})"


class RestockSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='restock_subscriptions')
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField()
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'restock_subscriptions'
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['product', 'email'], name='unique_restock_sub_per_email')]

    def __str__(self):
        return f'Restock sub for {self.product.name} ({self.email})'
