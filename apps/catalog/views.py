from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.core.cache import cache
from django.db import transaction
import django_filters
from django.db.models import Q
from django.utils import timezone
from .models import Category, CategoryChangeRequest, Product
from .serializers import (
    CategorySerializer, CategoryChangeRequestSerializer,
    ProductListSerializer, ProductDetailSerializer,
    RestockSubscriptionSerializer, SellerInfoSerializer
)
from apps.users.models import User
from apps.users.permissions import IsStoreAdmin
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied
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
        # Return only root categories (no parent) that are active AND approved
        return Category.objects.filter(parent__isnull=True, is_active=True, approval_status='APPROVED')

    def list(self, request, *args, **kwargs):
        cache_key = 'catalog:categories:v1'
        data = cache.get(cache_key)
        if data is None:
            queryset = self.filter_queryset(self.get_queryset())
            data = list(CategorySerializer(queryset, many=True).data)
            cache.set(cache_key, data, timeout=300)
        return Response(data)

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
            cache.delete('catalog:categories:v1')
            return Response(CategorySerializer(existing).data, status=status.HTTP_200_OK)

        category = Category(name=name, parent=parent)
        category.save()
        cache.delete('catalog:categories:v1')
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
            from django.db import connection
            if connection.vendor == 'postgresql':
                # The generated tsvector column and GIN index are created in migration 0009.
                # Include category-name matches for parity with the SQLite fallback.
                qs = qs.extra(
                    select={
                        'rank': "ts_rank(search_vector, plainto_tsquery('simple', %s))",
                    },
                    select_params=[search],
                    where=[
                        "(search_vector @@ plainto_tsquery('simple', %s) "
                        "OR category_id IN (SELECT id FROM categories WHERE name ILIKE %s))"
                    ],
                    params=[search, f'%{search}%'],
                    order_by=['-rank'],
                )
                return qs
            return qs.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(category__name__icontains=search)
            )

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
    ordering_fields = ['base_price', 'created_at', 'average_rating', 'ranking', 'sales_count']


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
        if user.is_authenticated and (
            getattr(user, 'is_staff', False) or getattr(user, 'role', None) == 'ADMIN'
        ):
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
        if upload.size > 5 * 1024 * 1024:
            return Response({'error': 'CSV file must be 5 MB or smaller.'}, status=status.HTTP_400_BAD_REQUEST)
        text = upload.read().decode('utf-8', errors='replace')
        reader = csv.DictReader(text.splitlines())
        seller = request.user if getattr(request.user, 'role', None) == 'SELLER' else None
        created = 0
        inventory_created = 0
        inventory_updated = 0
        errors = []
        for idx, row in enumerate(reader, start=2):
            row_created = 0
            row_inventory_created = 0
            row_inventory_updated = 0
            try:
                with transaction.atomic():
                    product_slug = (row.get('product_slug') or row.get('slug') or '').strip()
                    sku = (row.get('sku') or '').strip()
                    quantity_raw = row.get('quantity')
                    if quantity_raw in (None, ''):
                        quantity_raw = row.get('stock')
                    if product_slug and quantity_raw in (None, ''):
                        raise ValueError('quantity is required when product_slug is provided')
                    quantity = int(quantity_raw or 0)
                    if quantity < 0:
                        raise ValueError('quantity cannot be negative')
                    threshold_raw = row.get('low_stock_threshold')
                    threshold = int(threshold_raw) if threshold_raw not in (None, '') else None
                    if threshold is not None and threshold < 0:
                        raise ValueError('low_stock_threshold cannot be negative')
                    variant = (row.get('variant') or row.get('variant_label') or 'Default').strip()

                    product = None
                    if product_slug:
                        # Inventory-only rows update an existing product's variant.
                        product_qs = Product.objects.filter(slug=product_slug)
                        if seller is not None:
                            product_qs = product_qs.filter(seller=seller)
                        product = product_qs.first()
                        if product is None:
                            raise ValueError(f'product_slug "{product_slug}" not found')
                        if not sku:
                            raise ValueError('sku is required when product_slug is provided')
                    else:
                        name = (row.get('name') or '').strip()
                        if not name:
                            raise ValueError('missing name or product_slug')
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
                        row_created += 1

                    if sku:
                        inventory, inv_created = Inventory.objects.get_or_create(
                            sku=sku,
                            defaults={
                                'product': product,
                                'variant_label': variant or 'Default',
                                'quantity_available': quantity,
                                'low_stock_threshold': threshold if threshold is not None else 5,
                            },
                        )
                        if not inv_created and inventory.product_id != product.id:
                            raise ValueError(f'sku "{sku}" belongs to another product')
                        if not inv_created:
                            inventory.quantity_available = quantity
                            inventory.variant_label = variant or inventory.variant_label
                            if threshold is not None:
                                inventory.low_stock_threshold = threshold
                            inventory.save()
                            row_inventory_updated += 1
                        else:
                            row_inventory_created += 1
                created += row_created
                inventory_created += row_inventory_created
                inventory_updated += row_inventory_updated
            except Exception as e:
                errors.append({'row': idx, 'error': str(e)})
        return Response({
            'created': created,
            'inventory_created': inventory_created,
            'inventory_updated': inventory_updated,
            'errors': errors,
        })

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import ProductAdminSerializer, InventoryAdminSerializer, ProductImageSerializer
from .models import Inventory, ProductImage


class IsAdminOrSeller(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, 'role', None) in ('ADMIN', 'SELLER')
                or getattr(user, 'is_staff', False)
            )
        )


class AdminProductViewSet(viewsets.ModelViewSet):
    """Admin API for Products. Admins see all; sellers see and manage only their own."""
    serializer_class = ProductAdminSerializer
    permission_classes = [IsAdminOrSeller]

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

    def perform_update(self, serializer):
        if getattr(self.request.user, 'role', None) == 'SELLER':
            new_seller = serializer.validated_data.get('seller', serializer.instance.seller)
            if new_seller is None or new_seller.id != self.request.user.id:
                raise permissions.PermissionDenied('You cannot transfer product ownership.')
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
    permission_classes = [IsAdminOrSeller]

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
                raise PermissionDenied('You can only add inventory to your own products.')
        serializer.save()

    def perform_update(self, serializer):
        if getattr(self.request.user, 'role', None) == 'SELLER':
            product = serializer.validated_data.get('product', serializer.instance.product)
            if product is None or product.seller_id != self.request.user.id:
                raise PermissionDenied('You can only update inventory for your own products.')
        serializer.save()


class AdminCategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Categories with approval workflow.
    Admins: full immediate CRUD.
    Sellers: create goes to PENDING; edit/delete create change requests.
    """
    serializer_class = CategorySerializer
    pagination_class = None
    permission_classes = [IsAdminOrSeller]
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
        user = self.request.user

        # Sellers see: all approved categories + their own pending/rejected ones
        if getattr(user, 'role', None) == 'SELLER':
            qs = qs.filter(
                Q(approval_status='APPROVED') | Q(owner=user)
            )

        active_only = self.request.query_params.get('active_only')
        if active_only in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)

        # Filter by approval status if requested (for admin tab filtering)
        status_filter = self.request.query_params.get('approval_status')
        if status_filter:
            qs = qs.filter(approval_status=status_filter)

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

        user = request.user
        is_admin = getattr(user, 'role', None) == 'ADMIN'

        existing = Category.objects.filter(name__iexact=name, parent=parent).first()
        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.save()
            cache.delete('catalog:categories:v1')
            return Response(CategorySerializer(existing).data, status=status.HTTP_200_OK)

        category = Category(
            name=name,
            parent=parent,
            owner=None if is_admin else user,
            approval_status='APPROVED' if is_admin else 'PENDING',
        )
        category.save()

        if is_admin:
            cache.delete('catalog:categories:v1')
            return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)
        else:
            return Response({
                **CategorySerializer(category).data,
                'message': 'Category submitted for admin approval.',
            }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        is_admin = getattr(user, 'role', None) == 'ADMIN'

        if is_admin:
            # Admin edits take effect immediately
            response = super().update(request, *args, **kwargs)
            cache.delete('catalog:categories:v1')
            return response

        # Seller: create a change request instead of modifying directly
        category = self.get_object()
        proposed = {}
        for field in ('name', 'parent', 'is_active'):
            if field in request.data:
                proposed[field] = request.data[field]

        if not proposed:
            return Response({'error': 'No changes proposed.'}, status=status.HTTP_400_BAD_REQUEST)

        change_req = CategoryChangeRequest.objects.create(
            category=category,
            requested_by=user,
            change_type='EDIT',
            proposed_changes=proposed,
        )
        return Response({
            'message': 'Edit request submitted for admin approval.',
            'change_request_id': str(change_req.id),
        }, status=status.HTTP_202_ACCEPTED)

    def partial_update(self, request, *args, **kwargs):
        # Route PATCH through the same approval logic as PUT
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._auth_ok(request):
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        is_admin = getattr(user, 'role', None) == 'ADMIN'
        category = self.get_object()

        if is_admin:
            # Admin deletes take effect immediately
            if category.products.exists():
                category.is_active = False
                category.save()
                cache.delete('catalog:categories:v1')
                return Response({'message': 'Category has associated products and was marked inactive.', 'is_active': False}, status=status.HTTP_200_OK)
            category.delete()
            cache.delete('catalog:categories:v1')
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Seller: create a delete change request
        change_req = CategoryChangeRequest.objects.create(
            category=category,
            requested_by=user,
            change_type='DELETE',
        )
        return Response({
            'message': 'Delete request submitted for admin approval.',
            'change_request_id': str(change_req.id),
        }, status=status.HTTP_202_ACCEPTED)


class CategoryApprovalView(APIView):
    """Admin-only: approve or reject a pending category creation."""
    permission_classes = [IsAdminOrSeller]

    def _require_admin(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or getattr(user, 'role', None) != 'ADMIN':
            return False
        return True

    def post(self, request, pk):
        """Approve a pending category."""
        if not self._require_admin(request):
            return Response({'error': 'Only administrators can approve categories.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            category = Category.objects.get(id=pk)
        except Category.DoesNotExist:
            return Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)

        category.approval_status = 'APPROVED'
        category.rejection_reason = ''
        category.save()
        cache.delete('catalog:categories:v1')
        return Response(CategorySerializer(category).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Reject a pending category with optional reason."""
        if not self._require_admin(request):
            return Response({'error': 'Only administrators can reject categories.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            category = Category.objects.get(id=pk)
        except Category.DoesNotExist:
            return Response({'error': 'Category not found.'}, status=status.HTTP_404_NOT_FOUND)

        reason = (request.data.get('reason') or '').strip()
        category.approval_status = 'REJECTED'
        category.rejection_reason = reason
        category.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_200_OK)


class ChangeRequestListView(generics.ListAPIView):
    """Admin-only: list all category change requests."""
    serializer_class = CategoryChangeRequestSerializer
    permission_classes = [IsAdminOrSeller]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        qs = CategoryChangeRequest.objects.select_related('category', 'requested_by', 'reviewed_by')
        if getattr(user, 'role', None) == 'SELLER':
            # Sellers only see their own change requests
            qs = qs.filter(requested_by=user)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class ChangeRequestApprovalView(APIView):
    """Admin-only: approve or reject a category change request (edit/delete)."""
    permission_classes = [IsAdminOrSeller]

    def _require_admin(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or getattr(user, 'role', None) != 'ADMIN':
            return False
        return True

    def post(self, request, pk):
        """Approve a change request — apply the proposed changes."""
        if not self._require_admin(request):
            return Response({'error': 'Only administrators can approve change requests.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            cr = CategoryChangeRequest.objects.select_related('category').get(id=pk)
        except CategoryChangeRequest.DoesNotExist:
            return Response({'error': 'Change request not found.'}, status=status.HTTP_404_NOT_FOUND)

        if cr.status != 'PENDING':
            return Response({'error': 'This change request has already been reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        if cr.change_type == 'EDIT':
            for key, val in cr.proposed_changes.items():
                if key in ('name', 'is_active'):
                    setattr(cr.category, key, val)
                elif key == 'parent':
                    cr.category.parent_id = val
            cr.category.save()
        elif cr.change_type == 'DELETE':
            if cr.category.products.exists():
                cr.category.is_active = False
                cr.category.save()
            else:
                cr.category.delete()

        cr.status = 'APPROVED'
        cr.reviewed_by = request.user
        cr.reviewed_at = timezone.now()
        cr.save()
        cache.delete('catalog:categories:v1')
        return Response(CategoryChangeRequestSerializer(cr).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Reject a change request with optional reason."""
        if not self._require_admin(request):
            return Response({'error': 'Only administrators can reject change requests.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            cr = CategoryChangeRequest.objects.get(id=pk)
        except CategoryChangeRequest.DoesNotExist:
            return Response({'error': 'Change request not found.'}, status=status.HTTP_404_NOT_FOUND)

        if cr.status != 'PENDING':
            return Response({'error': 'This change request has already been reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '').strip()
        cr.status = 'REJECTED'
        cr.rejection_reason = reason
        cr.reviewed_by = request.user
        cr.reviewed_at = timezone.now()
        cr.save()
        return Response(CategoryChangeRequestSerializer(cr).data, status=status.HTTP_200_OK)
