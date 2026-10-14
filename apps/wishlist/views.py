from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from .models import WishlistItem


class WishlistView(APIView):
    """GET /api/v1/wishlist/ — list the current user's wishlist items."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = request.user.wishlist_items.select_related('product', 'product__category').prefetch_related('product__images')
        data = [
            {
                'id': str(w.id),
                'product_id': str(w.product.id),
                'product_slug': w.product.slug,
                'product_name': w.product.name,
                'base_price': w.product.base_price,
                'primary_image': (
                    request.build_absolute_uri(w.product.images.filter(is_primary=True).first().image.url)
                    if w.product.images.filter(is_primary=True).exists()
                    else None
                ),
                'created_at': w.created_at,
            }
            for w in items
        ]
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
