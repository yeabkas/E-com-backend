from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from django.db.models import Q
from .models import Category, Product
from .serializers import (
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    RestockSubscriptionSerializer, SellerInfoSerializer
)
from apps.users.models import User
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
import csv
from django.utils.text import slugify as _slugify
from decimal import Decimal as DDecimal


class CategoryListView(generics.ListCreateAPIView):
    """
    GET /api/v1/catalog/categories/
    List active root categories with their nested subcategories.
    POST /api/v1/catalog/categories/
    Define a new category.
    """
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        # Return only root categories (no parent) that are active
        return Category.objects.filter(parent__isnull=True, is_active=True)

    def create(self, request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or getattr(user, 'role', None) not in ('ADMIN', 'SELLER'):
            return Response({'error': 'Authentication as Admin or Seller required.'}, status=status.HTTP_403_FORBIDDEN)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Category name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent_id = request.data.get('parent')
        parent = None
        if parent_id:
            try:
                parent = Category.objects.get(id=parent_id)
            except (Category.DoesNotExist, ValueError):
                return Response({'error': 'Parent category not found.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = Category.objects.filter(name__iexact=name, parent=parent).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save()
            return Response(CategorySerializer(existing).data, status=status.HTTP_200_OK)

        category = Category(name=name, parent=parent)
        category.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class ProductFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name="base_price", lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name="base_price", lookup_expr='lte')
    category = django_filters.CharFilter(field_name="category__slug")
    seller = django_filters.UUIDFilter(field_name="seller__id")

    class Meta:
        model = Product
        fields = ['category', 'min_price', 'max_price', 'seller']


class ProductListView(generics.ListAPIView):
    """
    GET /api/v1/catalog/products/
    List active products with filtering, searching, and ordering.
    """
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ProductFilter

    def get_queryset(self):
        # Only return active products, prefetch related to optimize queries
        qs = Product.objects.filter(is_active=True).select_related('category', 'seller').prefetch_related('images')

        seller_id = self.request.query_params.get('seller') or self.request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(category__name__icontains=search))
            from django.db import connection
            if connection.vendor == 'postgresql':
                from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
                vector = SearchVector('name', weight='A') + SearchVector('description', weight='B')
                rank = SearchRank(vector, SearchQuery(search))
                qs = qs.annotate(rank=rank).order_by('-rank')
            return qs

        ranked_only = self.request.query_params.get('ranked_only')
        if ranked_only:
            return qs.filter(ranking__gt=0).order_by('ranking', '-created_at')

        landing = self.request.query_params.get('landing')
        if landing:
            from django.db.models import Case, When, Value, IntegerField
            return qs.annotate(
                has_rank=Case(
                    When(ranking__gt=0, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField()
                )
            ).order_by('has_rank', 'ranking', '-created_at')

        return qs

    search_fields = ['name', 'description']
    ordering_fields = ['base_price', 'created_at', 'average_rating', 'ranking']


class SellerListView(generics.ListAPIView):
    """
    GET /api/v1/catalog/sellers/
    List active shops/sellers with product count, profile picture, etc.
    """
    serializer_class = SellerInfoSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        qs = User.objects.filter(
            Q(role='SELLER') | Q(products__isnull=False),
            is_active=True,
            is_suspended=False
        ).distinct()

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search)
            )

        return qs.order_by('-created_at')


class SellerDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/catalog/sellers/<pk>/
    Get public seller/shop profile by user ID.
    """
    serializer_class = SellerInfoSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'pk'

    def get_queryset(self):
        return User.objects.filter(is_active=True, is_suspended=False)


class ProductDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/catalog/products/{slug}/
    Get product details by slug.
    """
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        # Include inactive products if user is admin, else only active
        user = self.request.user
        qs = Product.objects.select_related('category', 'seller').prefetch_related('images', 'variants')
        if user.is_authenticated and getattr(user, 'is_staff', False):
            return qs
        return qs.filter(is_active=True)


class RestockSubscriptionCreateView(generics.CreateAPIView):
    serializer_class = RestockSubscriptionSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request, 'user', None) and self.request.user.is_authenticated else None
        serializer.save(user=user)


class AdminProductImportView(APIView):
    permission_classes = [AllowAny]

    def _auth_ok(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'role', None) not in ('ADMIN', 'SELLER'):
            return False
        return True

    def post(self, request):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        upload = request.FILES.get('file')
        if not upload:
            return Response({'error': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)
        text = upload.read().decode('utf-8', errors='replace')
        reader = csv.DictReader(text.splitlines())
        seller = request.user if getattr(request.user, 'role', None) == 'SELLER' else None
        created = 0
        errors = []
        for idx, row in enumerate(reader, start=2):
            try:
                name = (row.get('name') or '').strip()
                if not name:
                    raise ValueError('missing name')
                cat_name = (row.get('category') or '').strip()
                if cat_name:
                    cat = Category.objects.filter(is_active=True).filter(name__iexact=cat_name).first()
                    if cat is None:
                        cat = Category.objects.create(name=cat_name)
                else:
                    cat = Category.objects.filter(is_active=True).first()
                    if cat is None:
                        cat = Category.objects.create(name='General')
                price_raw = row.get('price') or row.get('base_price') or '0'
                base_price = DDecimal(price_raw)
                is_active_str = (row.get('is_active') or 'true').strip().lower()
                product = Product.objects.create(
                    name=name,
                    description=(row.get('description') or '').strip(),
                    base_price=base_price,
                    category=cat,
                    is_active=is_active_str in ('1', 'true', 'yes'),
                    seller=seller,
                )
                created += 1
            except Exception as e:
                errors.append({'row': idx, 'error': str(e)})
        return Response({'created': created, 'errors': errors})

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import ProductAdminSerializer, InventoryAdminSerializer, ProductImageSerializer
from .models import Inventory, ProductImage


class IsAdminOrSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ('ADMIN', 'SELLER')
        )


class AdminProductViewSet(viewsets.ModelViewSet):
    """Admin API for Products. Admins see all; sellers see and manage only their own."""
    serializer_class = ProductAdminSerializer
    permission_classes = [AllowAny]

    def _auth_ok(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'role', None) not in ('ADMIN', 'SELLER'):
            return False
        return True
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'slug']
    ordering_fields = ['created_at', 'ranking', 'base_price', 'name']

    @action(detail=False, methods=['post'], url_path='set-ranking')
    def set_ranking(self, request):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        if getattr(request.user, 'role', None) != 'ADMIN':
            return Response({'error': 'Only administrators can configure landing page ranking.'}, status=status.HTTP_403_FORBIDDEN)

        rankings = request.data.get('rankings')
        if isinstance(rankings, list):
            for item in rankings:
                pid = item.get('id')
                rank = item.get('ranking', 0)
                if pid:
                    Product.objects.filter(id=pid).update(ranking=max(0, int(rank)))
            return Response({'status': 'Rankings updated successfully.'}, status=status.HTTP_200_OK)

        product_id = request.data.get('product_id')
        if product_id:
            rank = int(request.data.get('ranking', 0))
            Product.objects.filter(id=product_id).update(ranking=max(0, rank))
            return Response({'status': 'Ranking updated successfully.'}, status=status.HTTP_200_OK)

        return Response({'error': 'Invalid payload.'}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self):
        qs = Product.objects.all()
        if getattr(self.request.user, 'role', None) == 'SELLER':
            return qs.filter(seller=self.request.user)
        return qs

    def perform_create(self, serializer):
        if getattr(self.request.user, 'role', None) == 'SELLER':
            serializer.save(seller=self.request.user)
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='images')
    def upload_images(self, request, pk=None):
        """POST /catalog/admin/products/{id}/images/ — multipart 'images' files."""
        product = self.get_object()
        files = request.FILES.getlist('images')
        if not files:
            return Response({'error': "No files provided under the 'images' field."}, status=status.HTTP_400_BAD_REQUEST)

        import base64
        import io
        from PIL import Image

        created = []
        existing = product.images.count()
        for i, f in enumerate(files):
            # Process & optimize image with Pillow to create base64 data URI
            try:
                im = Image.open(f)
                im.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                out_fmt = 'PNG' if getattr(im, 'format', None) == 'PNG' else 'JPEG'
                if out_fmt == 'JPEG' and im.mode in ('RGBA', 'P', 'LA'):
                    im = im.convert('RGB')
                out_buf = io.BytesIO()
                im.save(out_buf, format=out_fmt, quality=85, optimize=True)
                b64_str = base64.b64encode(out_buf.getvalue()).decode('utf-8')
                mime = 'image/png' if out_fmt == 'PNG' else 'image/jpeg'
                data_uri = f"data:{mime};base64,{b64_str}"
            except Exception:
                f.seek(0)
                content = f.read()
                content_type = getattr(f, 'content_type', 'image/jpeg') or 'image/jpeg'
                b64_str = base64.b64encode(content).decode('utf-8')
                data_uri = f"data:{content_type};base64,{b64_str}"

            alt_text = request.data.get('alt_text', '') or product.name
            is_primary = (existing == 0 and i == 0)

            # Save with disk file if writable; gracefully fallback to database-only image_data on read-only environments
            try:
                f.seek(0)
                img = ProductImage.objects.create(
                    product=product,
                    image=f,
                    image_data=data_uri,
                    alt_text=alt_text,
                    is_primary=is_primary,
                    order=existing + i,
                )
            except Exception:
                img = ProductImage.objects.create(
                    product=product,
                    image=None,
                    image_data=data_uri,
                    alt_text=alt_text,
                    is_primary=is_primary,
                    order=existing + i,
                )
            created.append(img)
        return Response(ProductImageSerializer(created, many=True, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='images/(?P<image_id>[^/.]+)')
    def delete_image(self, request, pk=None, image_id=None):
        product = self.get_object()
        try:
            img = product.images.get(id=image_id)
        except ProductImage.DoesNotExist:
            return Response({'error': 'Image not found.'}, status=status.HTTP_404_NOT_FOUND)
        was_primary = img.is_primary
        img.delete()
        if was_primary:
            first = product.images.first()
            if first:
                first.is_primary = True
                first.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

class AdminInventoryViewSet(viewsets.ModelViewSet):
    """Admin API for Inventory. Sellers see only inventory of their own products."""
    serializer_class = InventoryAdminSerializer
    permission_classes = [AllowAny]

    def _auth_ok(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'role', None) not in ('ADMIN', 'SELLER'):
            return False
        return True
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['product']
    search_fields = ['sku', 'variant_label']

    def get_queryset(self):
        qs = Inventory.objects.all()
        if getattr(self.request.user, 'role', None) == 'SELLER':
            return qs.filter(product__seller=self.request.user)
        return qs

    def perform_create(self, serializer):
        if getattr(self.request.user, 'role', None) == 'SELLER':
            product = serializer.validated_data.get('product')
            if product is None or product.seller_id != self.request.user.id:
                # pyrefly: ignore [missing-attribute]
                raise permissions.PermissionDenied('You can only add inventory to your own products.')
        serializer.save()


class AdminCategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Categories.
    Admins & Sellers can list, create, update, and delete categories.
    """
    serializer_class = CategorySerializer
    pagination_class = None
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'slug']
    ordering_fields = ['name', 'created_at']

    def _auth_ok(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'role', None) not in ('ADMIN', 'SELLER'):
            return False
        return True

    def get_queryset(self):
        qs = Category.objects.all().order_by('name')
        active_only = self.request.query_params.get('active_only')
        if active_only in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        return qs

    def create(self, request, *args, **kwargs):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Category name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        parent_id = request.data.get('parent')
        parent = None
        if parent_id:
            try:
                parent = Category.objects.get(id=parent_id)
            except (Category.DoesNotExist, ValueError):
                return Response({'error': 'Parent category not found.'}, status=status.HTTP_400_BAD_REQUEST)

        existing = Category.objects.filter(name__iexact=name, parent=parent).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save()
            return Response(CategorySerializer(existing).data, status=status.HTTP_200_OK)

        category = Category(name=name, parent=parent)
        category.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        category = self.get_object()
        if category.products.exists():
            category.is_active = False
            category.save()
            return Response({'message': 'Category has associated products and was marked inactive.', 'is_active': False}, status=status.HTTP_200_OK)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

