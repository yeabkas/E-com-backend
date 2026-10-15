from rest_framework import viewsets, mixins, status, permissions
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from decimal import Decimal
from .models import Order, OrderItem
from .serializers import OrderSerializer, CheckoutSerializer, ShippingMethodSerializer
from .models import Order, OrderItem, ShippingMethod
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.generics import ListAPIView
from django.db.models import Sum, Count
from apps.cart.models import Cart
from apps.catalog.models import Inventory

class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    API for listing user's past orders and executing checkout.
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own orders
        return Order.objects.filter(user=self.request.user).prefetch_related('items')

    @action(detail=False, methods=['POST'])
    def checkout(self, request):
        """
        Converts the user's active cart into a confirmed Order.
        Validates stock, decrements inventory, captures shipping snapshot, and clears the cart.
        """
        serializer = CheckoutSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        shipping_address = serializer.validated_data['shipping_address_id']
        method_id = serializer.validated_data.get('shipping_method_id')
        shipping_method = None
        if method_id:
            shipping_method = ShippingMethod.objects.filter(id=method_id, is_active=True).first()
        if shipping_method is None:
            shipping_method = ShippingMethod.objects.filter(is_active=True).order_by('price').first()
        user = request.user

        if not user.is_verified:
            return Response({"error": "Please verify your email address before checking out."}, status=status.HTTP_403_FORBIDDEN)

        try:
            cart = Cart.objects.prefetch_related('items__inventory__product').get(user=user)
        except Cart.DoesNotExist:
            return Response({"error": "No active cart found for checkout."}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = cart.items.all()
        if not cart_items:
            return Response({"error": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. Create the Order
                order = Order.objects.create(
                    user=user,
                    status=Order.OrderStatus.PENDING,
                )
                order.populate_shipping_snapshot(shipping_address)

                subtotal = Decimal('0.00')

                # 2. Iterate cart items, check stock, decrement inventory, create order items
                from django.db import connection
                for item in cart_items:
                    # Re-fetch inventory with select_for_update to lock the row during checkout (Requires PostgreSQL)
                    if connection.vendor == 'postgresql':
                        inventory = Inventory.objects.select_for_update().get(id=item.inventory.id)
                    else:
                        inventory = Inventory.objects.get(id=item.inventory.id)
                    
                    if inventory.quantity_available < item.quantity:
                        raise ValueError(f"Insufficient stock for {inventory.product.name} ({inventory.sku})")
                    
                    # Decrement available, increment reserved
                    inventory.quantity_available -= item.quantity
                    inventory.quantity_reserved += item.quantity
                    inventory.save()

                    unit_price = inventory.product.base_price
                    subtotal += (unit_price * item.quantity)

                    OrderItem.objects.create(
                        order=order,
                        product_id=inventory.product.id,
                        product_name=inventory.product.name,
                        sku=inventory.sku,
                        variant_label=inventory.variant_label,
                        quantity=item.quantity,
                        unit_price=unit_price
                    )

                # 3. Finalize Order totals (shipping via selected method)
                order.subtotal = subtotal
                order.shipping_amount = shipping_method.cost_for(subtotal) if shipping_method is not None else Decimal('0.00')
                order.tax_amount = Decimal('0.00')
                order.shipping_method_name = shipping_method.name if shipping_method is not None else ''

                # Apply the cart's coupon, if any
                discount = Decimal('0.00')
                if cart.coupon is not None:
                    scoped_subtotal = sum(
                        item.item_total for item in cart_items
                        if cart.coupon.applies_to(item.inventory.product)
                    )
                    ok, _msg = cart.coupon.is_valid_for(scoped_subtotal, user=user)
                    if ok and scoped_subtotal > 0:
                        discount = cart.coupon.discount_for(scoped_subtotal)
                        if cart.coupon.type == cart.coupon.Type.FREE_SHIPPING:
                            order.shipping_amount = Decimal('0.00')
                        order.coupon_code = cart.coupon.code
                        order.discount_amount = discount
                        from apps.promotions.models import CouponUsage
                        CouponUsage.objects.create(coupon=cart.coupon, user=user, order=order)

                order.total_amount = subtotal - discount + order.shipping_amount + order.tax_amount
                order.save()

                # 4. Clear the cart
                cart.delete()

                return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "An unexpected error occurred during checkout."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """PI Admin order management for support and fulfillment."""
    serializer_class = OrderSerializer
    permission_classes = [IsAdminUser]
    queryset = Order.objects.all()
    filterset_fields = ['status']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['POST'])
    def transition(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        if not new_status:
            return Response({"error": "status is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order.transition_to(new_status)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from apps.orders.tasks import send_order_receipt_email, send_order_shipping_email
            if new_status == Order.OrderStatus.PAID:
                send_order_receipt_email.delay(str(order.id))
            elif new_status == Order.OrderStatus.SHIPPED:
                send_order_shipping_email.delay(str(order.id))
        except Exception:
            pass
        return Response(OrderSerializer(order).data)


class ShippingMethodListView(ListAPIView):
    serializer_class = ShippingMethodSerializer
    permission_classes = [AllowAny]
    queryset = ShippingMethod.objects.filter(is_active=True)
    pagination_class = None


class AdminShippingMethodViewSet(viewsets.ModelViewSet):
    serializer_class = ShippingMethodSerializer
    permission_classes = [IsAdminUser]
    queryset = ShippingMethod.objects.all()


class SellerSalesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        from apps.catalog.models import Product
        if getattr(user, 'role', None) == 'SELLER':
            product_ids = Product.objects.filter(seller=user).values_list('id', flat=True)
        else:
            product_ids = Product.objects.all().values_list('id', flat=True)
        items = OrderItem.objects.filter(product_id__in=product_ids).select_related('order').order_by('-order__created_at')
        payload = []
        for it in items:
            payload.append({
                'order_id': str(it.order.id),
                'order_status': it.order.status,
                'order_created_at': it.order.created_at,
                'product_id': str(it.product_id) if it.product_id else None,
                'product_name': it.product_name,
                'quantity': it.quantity,
                'unit_price': it.unit_price,
                'total_price': it.total_price,
            })
        return Response(payload)


class AdminMetricsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, 'role', None) not in ('ADMIN', 'SELLER') and not getattr(user, 'is_staff', False):
            return Response({'error': 'Admin or Seller access required.'}, status=status.HTTP_403_FORBIDDEN)

        from apps.catalog.models import Product
        from apps.catalog.serializers import ProductListSerializer

        if getattr(user, 'role', None) == 'SELLER':
            product_ids = Product.objects.filter(seller=user).values_list('id', flat=True)
            seller_items = OrderItem.objects.filter(
                product_id__in=product_ids,
                order__status__in=[
                    Order.OrderStatus.PAID, Order.OrderStatus.PROCESSING,
                    Order.OrderStatus.SHIPPED, Order.OrderStatus.DELIVERED, Order.OrderStatus.COMPLETED
                ]
            )
            revenue_total = seller_items.aggregate(total=Sum('total_price'))['total'] or 0
            order_count = Order.objects.filter(items__product_id__in=product_ids).distinct().count()
            top = Product.objects.filter(seller=user).order_by('-sales_count')[:10]
            return Response({
                'revenue': revenue_total,
                'orders_by_status': {'COMPLETED': order_count},
                'funnel': [{'status': 'COMPLETED', 'count': order_count}],
                'top_products': ProductListSerializer(top, many=True, context={'request': request}).data,
            })

        revenue_total = Order.objects.filter(
            status__in=[Order.OrderStatus.PAID, Order.OrderStatus.PROCESSING,
                        Order.OrderStatus.SHIPPED, Order.OrderStatus.DELIVERED, Order.OrderStatus.COMPLETED]
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        funnel = list(Order.objects.values('status').annotate(count=Count('id')))
        orders_by_status = {f['status']: f['count'] for f in funnel}
        top = Product.objects.order_by('-sales_count')[:10]
        return Response({
            'revenue': revenue_total,
            'funnel': funnel,
            'orders_by_status': orders_by_status,
            'top_products': ProductListSerializer(top, many=True, context={'request': request}).data,
        })
