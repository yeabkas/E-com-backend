from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Inventory, RestockSubscription, Product
from apps.orders.models import Order

UNPAID_ORDER_TTL = timedelta(hours=1)


@shared_task
def expire_unpaid_orders():
    """Cancel PENDING orders older than UNPAID_ORDER_TTL and release their reserved stock."""
    cutoff = timezone.now() - UNPAID_ORDER_TTL
    stale = Order.objects.filter(status=Order.OrderStatus.PENDING, created_at__lt=cutoff)
    cancelled = 0
    for order in stale:
        with transaction.atomic():
            for item in order.items.all():  # type: ignore[attr-defined]
                inv = Inventory.objects.filter(sku=item.sku).first()
                if inv is not None:
                    inv.quantity_available += item.quantity
                    inv.quantity_reserved = max(inv.quantity_reserved - item.quantity, 0)
                    inv.save(update_fields=['quantity_available', 'quantity_reserved'])
            order.transition_to(Order.OrderStatus.CANCELLED)
            cancelled += 1

    # Expire abandoned anonymous carts (no user) older than 7 days
    from apps.cart.models import Cart
    cart_cutoff = timezone.now() - timedelta(days=7)
    Cart.objects.filter(user__isnull=True, updated_at__lt=cart_cutoff).delete()

    return cancelled


@shared_task
def send_order_receipt_email(order_id: str) -> bool:
    """Send an order receipt email via the configured email backend."""
    from django.core.mail import send_mail
    from apps.orders.models import Order
    try:
        order = Order.objects.select_related('user').get(id=order_id)
    except Order.DoesNotExist:
        return False
    lines = [f"Order {order.id} confirmed. Total: ETB {order.total_amount}"]
    send_mail(
        subject=f'GASH E-COM: Order {str(order.id)[:8]} receipt',
        message='\n'.join(lines),
        from_email=None,
        recipient_list=[order.user.email],
    )
    return True


@shared_task
def send_restock_notifications(product_id: str) -> int:
    from django.core.mail import send_mail
    from apps.catalog.models import Product
    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return 0
    subs = RestockSubscription.objects.filter(product=product, notified=False)
    sent = 0
    for sub in subs:
        try:
            send_mail(
                subject=f'GASH E-COM: {product.name} is back in stock',
                message=f'{product.name} is available again. Visit: {product.slug}',
                from_email=None,
                recipient_list=[sub.email],
            )
            sub.notified = True
            sub.save(update_fields=['notified'])
            sent += 1
        except Exception:
            pass
    return sent


@shared_task
def send_low_stock_alerts() -> int:
    from django.core.mail import send_mail
    from apps.catalog.models import Inventory
    # Group low-stock items by product owner to send at most one email per owner group? Send list
    alerted = 0
    recipients_by_owner: dict = {}
    # Simplify: filter threshold individually
    low_items = [i for i in Inventory.objects.select_related('product','product__seller').all() if i.quantity_available <= i.low_stock_threshold]
    for inv in low_items:
        if inv.low_stock_alerted:
            continue
        seller = getattr(inv.product, 'seller', None)
        owner_email = seller.email if seller is not None else getattr(settings, 'DEFAULT_FROM_EMAIL', 'admin@example.com')
        recipients_by_owner.setdefault(owner_email, []).append((inv, seller))
    for owner_email, items in recipients_by_owner.items():
        lines = ['Low stock items:']
        for inv, seller in items:
            lines.append(f"- {inv.product.name} SKU {inv.sku}: {inv.quantity_available} left")
        try:
            send_mail(
                subject='GASH E-COM low-stock alert',
                message='\n'.join(lines),
                from_email=None,
                recipient_list=[owner_email],
            )
            for inv, _ in items:
                inv.low_stock_alerted = True
                inv.save(update_fields=['low_stock_alerted'])
            alerted += len(items)
        except Exception:
            pass
    return alerted


@shared_task
def send_order_shipping_email(order_id: str) -> bool:
    from django.core.mail import send_mail
    from apps.orders.models import Order
    try:
        order = Order.objects.select_related('user').get(id=order_id)
    except Order.DoesNotExist:
        return False
    send_mail(
        subject=f'GASH E-COM: Your order {str(order.id)[:8]} has shipped',
        message=f'Your order {order.id} is on its way.',
        from_email=None,
        recipient_list=[order.user.email],
    )
    return True
