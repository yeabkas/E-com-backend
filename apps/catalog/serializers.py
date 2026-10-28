from rest_framework import serializers
from .models import Category, CategoryChangeRequest, Product, ProductImage, Inventory, RestockSubscription
from apps.users.models import User


class SellerInfoSerializer(serializers.ModelSerializer):
    """Public seller information."""
    store_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone',
            'store_name', 'profile_picture', 'product_count',
            'is_verified', 'created_at'
        ]

    def get_store_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.email.split('@')[0]

    def get_profile_picture(self, obj):
        if obj.profile_picture:
            try:
                url = obj.profile_picture.url
                request = self.context.get('request')
                if request and not url.startswith('http'):
                    return request.build_absolute_uri(url)
                return url
            except Exception:
                return str(obj.profile_picture)
        return None

    def get_product_count(self, obj):
        if hasattr(obj, 'products'):
            return obj.products.filter(is_active=True).count()
        return 0


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer supporting nesting and category creation."""
    slug = serializers.SlugField(required=False, read_only=True)
    subcategories = serializers.SerializerMethodField(read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    product_count = serializers.SerializerMethodField(read_only=True)
    owner_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'parent', 'parent_name', 'subcategories',
            'product_count', 'is_active', 'approval_status', 'rejection_reason',
            'owner', 'owner_name'
        ]
        read_only_fields = ['id', 'slug']

    def get_subcategories(self, obj):
        if hasattr(obj, 'subcategories') and obj.subcategories.exists():
            return CategorySerializer(obj.subcategories.filter(is_active=True), many=True).data
        return []

    def get_product_count(self, obj):
        if hasattr(obj, 'products'):
            return obj.products.count()
        return 0

    def get_owner_name(self, obj):
        if obj.owner:
            name = f"{obj.owner.first_name} {obj.owner.last_name}".strip()
            return name if name else obj.owner.email
        return None


class CategoryChangeRequestSerializer(serializers.ModelSerializer):
    """Serializer for category change requests (edit/delete) pending admin approval."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    requested_by_name = serializers.SerializerMethodField(read_only=True)
    reviewed_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CategoryChangeRequest
        fields = [
            'id', 'category', 'category_name', 'change_type', 'proposed_changes',
            'status', 'rejection_reason', 'requested_by', 'requested_by_name',
            'created_at', 'reviewed_at', 'reviewed_by', 'reviewed_by_name'
        ]
        read_only_fields = ['id', 'requested_by', 'created_at', 'reviewed_at', 'reviewed_by']

    def get_requested_by_name(self, obj):
        u = obj.requested_by
        name = f"{u.first_name} {u.last_name}".strip()
        return name if name else u.email

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            name = f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}".strip()
            return name if name else obj.reviewed_by.email
        return None


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for product images."""
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']

    def get_image(self, obj):
        if getattr(obj, 'image_data', None):
            return obj.image_data
        request = self.context.get('request')
        if obj.image:
            try:
                if request:
                    return request.build_absolute_uri(obj.image.url)
                return obj.image.url
            except Exception:
                pass
        return None


class InventorySerializer(serializers.ModelSerializer):
    """Serializer for product variants/inventory."""
    
    class Meta:
        model = Inventory
        fields = ['id', 'sku', 'variant_label', 'quantity_available']


class ProductListSerializer(serializers.ModelSerializer):
    """Optimized serializer for listing products."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    seller = SellerInfoSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category', 'category_name',
            'base_price', 'primary_image', 'images', 'average_rating', 'review_count', 'sales_count',
            'seller', 'ranking'
        ]

    def get_primary_image(self, obj):
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image:
            if getattr(image, 'image_data', None):
                return image.image_data
            if image.image:
                try:
                    request = self.context.get('request')
                    if request:
                        return request.build_absolute_uri(image.image.url)
                    return image.image.url
                except Exception:
                    pass
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for a single product."""
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = InventorySerializer(many=True, read_only=True)
    seller = SellerInfoSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'category', 'description',
            'base_price', 'average_rating', 'review_count', 'sales_count',
            'images', 'variants', 'seller', 'ranking', 'created_at'
        ]


class ProductAdminSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    seller_info = SellerInfoSerializer(source='seller', read_only=True)
    seller_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__in=['SELLER', 'ADMIN']),
        source='seller',
        required=False,
        allow_null=True
    )

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['slug', 'seller', 'average_rating', 'review_count', 'sales_count', 'created_at', 'updated_at']


class InventoryAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = '__all__'


class RestockSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestockSubscription
        fields = ['product', 'email']
