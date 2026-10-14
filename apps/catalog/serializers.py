from rest_framework import serializers
from .models import Category, Product, ProductImage, Inventory, RestockSubscription
from apps.users.models import User


class SellerInfoSerializer(serializers.ModelSerializer):
    """Public seller information."""
    store_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'store_name']

    def get_store_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.email.split('@')[0]


class CategorySerializer(serializers.ModelSerializer):
    """Basic Category serializer."""
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'subcategories']

    def get_subcategories(self, obj):
        if obj.subcategories.exists():
            return CategorySerializer(obj.subcategories.filter(is_active=True), many=True).data
        return []


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for product images."""
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
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
        image = obj.images.filter(is_primary=True).first()
        if not image:
            image = obj.images.first()
        if image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(image.image.url)
            return image.image.url
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
