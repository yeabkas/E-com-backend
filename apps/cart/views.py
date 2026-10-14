from rest_framework import viewsets, status, throttling
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer, CartMergeSerializer


class CouponThrottle(throttling.ScopedRateThrottle):
    scope = 'coupons'


class CartViewSet(viewsets.GenericViewSet):
    """
    API for interacting with the user's shopping cart.
    Supports both anonymous (session-based) carts and authenticated carts.
    """
    queryset = Cart.objects.prefetch_related('items__inventory__product')
    
    def get_permissions(self):
        if self.action in ['merge']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_throttles(self):
        if self.action == 'apply_coupon':
            return [CouponThrottle()]
        return []

    def get_cart(self, request):
        """Retrieve the cart for the current user or session."""
        if request.user.is_authenticated:
            cart, created = Cart.objects.get_or_create(user=request.user)
            return cart
        else:
            # For anonymous users, the frontend should pass cart_id in headers or query params
            cart_id = request.headers.get('X-Cart-ID') or request.query_params.get('cart_id')
            if cart_id:
                try:
                    return Cart.objects.get(id=cart_id, user__isnull=True)
                except Cart.DoesNotExist:
                    pass
            # Create a new anonymous cart if none exists or provided ID is invalid
            return Cart.objects.create()

    @action(detail=False, methods=['GET'])
    def my_cart(self, request):
        """Get the current cart and its items."""
        cart = self.get_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['POST'])
    def add_item(self, request):
        """Add an item to the cart or update quantity if it exists."""
        cart = self.get_cart(request)
        serializer = CartItemSerializer(data=request.data)
        
        if serializer.is_valid():
            inventory = serializer.validated_data['inventory']
            quantity = serializer.validated_data['quantity']
            
            # Check stock
            if inventory.quantity_available < quantity:
                return Response(
                    {"error": "Not enough stock available."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Add or update item
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                inventory=inventory,
                defaults={'quantity': quantity}
            )
            
            if not created:
                if inventory.quantity_available < (cart_item.quantity + quantity):
                    return Response(
                        {"error": "Not enough stock available to add more."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                cart_item.quantity += quantity
                cart_item.save()
                
            cart_serializer = CartSerializer(cart)
            return Response(cart_serializer.data, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['PATCH'])
    def update_item(self, request):
        """Update the quantity of an item in the cart."""
        cart = self.get_cart(request)
        item_id = request.data.get('item_id')
        quantity = request.data.get('quantity')
        
        if not item_id or quantity is None:
            return Response({"error": "item_id and quantity are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            quantity = int(quantity)
            if quantity < 1:
                return Response({"error": "Quantity must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        
        if cart_item.inventory.quantity_available < quantity:
            return Response({"error": "Not enough stock available."}, status=status.HTTP_400_BAD_REQUEST)
            
        cart_item.quantity = quantity
        cart_item.save()
        
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['DELETE'])
    def remove_item(self, request):
        """Remove an item from the cart."""
        cart = self.get_cart(request)
        item_id = request.data.get('item_id')
        
        if not item_id:
            return Response({"error": "item_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
        cart_item.delete()
        
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['POST'])
    def apply_coupon(self, request):
        """Validate and attach a coupon to the user's cart."""
        cart = self.get_cart(request)
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response({"error": "code is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.promotions.models import Coupon
        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            return Response({"error": "Invalid coupon code."}, status=status.HTTP_404_NOT_FOUND)

        scoped = sum(
            item.item_total for item in cart.items.all()
            if coupon.applies_to(item.inventory.product)
        )
        if scoped <= 0:
            return Response({"error": "This coupon doesn't apply to any items in your cart."}, status=status.HTTP_400_BAD_REQUEST)
        ok, message = coupon.is_valid_for(scoped, user=request.user if request.user.is_authenticated else None)
        if not ok:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        cart.coupon = coupon
        cart.save(update_fields=['coupon', 'updated_at'])
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['POST'])
    def remove_coupon(self, request):
        cart = self.get_cart(request)
        cart.coupon = None
        cart.save(update_fields=['coupon', 'updated_at'])
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['POST'])
    def merge(self, request):
        """Merge an anonymous session cart into the authenticated user's cart."""
        serializer = CartMergeSerializer(data=request.data)
        if serializer.is_valid():
            session_cart_id = serializer.validated_data['session_cart_id']
            try:
                session_cart = Cart.objects.get(id=session_cart_id, user__isnull=True)
            except Cart.DoesNotExist:
                return Response({"error": "Invalid or already merged session cart."}, status=status.HTTP_400_BAD_REQUEST)
                
            user_cart, _ = Cart.objects.get_or_create(user=request.user)
            
            # Merge items
            for session_item in session_cart.items.all():
                user_item, created = CartItem.objects.get_or_create(
                    cart=user_cart,
                    inventory=session_item.inventory,
                    defaults={'quantity': session_item.quantity}
                )
                if not created:
                    user_item.quantity += session_item.quantity
                    user_item.save()
                    
            # Delete the anonymous cart
            session_cart.delete()
            
            return Response(CartSerializer(user_cart).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
