from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.catalog.serializers import ProductImageSerializer
from .models import WishlistItem


class WishlistView(APIView):
    """GET /api/v1/wishlist/ — list the current user's wishlist items."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = request.user.wishlist_items.select_related(
            'product', 'product__category'
        ).prefetch_related('product__images', 'product__variants')

        data = []
        for w in items:
            serialized_images = ProductImageSerializer(
                w.product.images.all(), many=True, context={'request': request}
            ).data

            primary_img = None
            for img in serialized_images:
                if img.get('is_primary') and img.get('image'):
                    primary_img = img['image']
                    break
            if not primary_img and serialized_images:
                for img in serialized_images:
                    if img.get('image'):
                        primary_img = img['image']
                        break

            first_inv = w.product.variants.filter(quantity_available__gt=0).first() or w.product.variants.first()
            data.append({
                'id': str(w.id),
                'product_id': str(w.product.id),
                'product_slug': w.product.slug,
                'product_name': w.product.name,
                'base_price': str(w.product.base_price),
                'category_name': w.product.category.name if w.product.category else 'General',
                'category_slug': w.product.category.slug if w.product.category else '',
                'average_rating': float(w.product.average_rating) if hasattr(w.product, 'average_rating') else 5.0,
                'review_count': getattr(w.product, 'review_count', 0),
                'primary_image': primary_img,
                'images': serialized_images,
                'in_stock': bool(first_inv and first_inv.quantity_available > 0),
                'inventory_id': str(first_inv.id) if first_inv else None,
                'created_at': w.created_at,
            })
        return Response(data)


class WishlistToggleView(APIView):
    """POST /api/v1/wishlist/toggle/ {product_id} — add or remove; returns wishlisted bool."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = Product.objects.get(id=product_id)
        except (Product.DoesNotExist, ValueError):
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.delete()
            return Response({'wishlisted': False})
        return Response({'wishlisted': True}, status=status.HTTP_201_CREATED)
