import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.models import Inventory, RestockSubscription, Product
from apps.orders.models import Order

UNPAID_ORDER_TTL = timedelta(hours=1)
logger = logging.getLogger(__name__)


def _send_templated_email(subject, text_template, html_template, context, recipients):
    """Send one multipart email. Returns True when the backend accepted it."""
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=None,
        to=list(dict.fromkeys(recipients)),
    )
    message.attach_alternative(html_body, 'text/html')
    message.send()
    return True


def _order_email_context(order):
    return {
        'order': order,
        'order_number': order.order_number,
        'items': list(order.items.all()),
        'frontend_url': settings.FRONTEND_URL.rstrip('/'),
    }



@shared_task
def expire_unpaid_orders():
    """Cancel PENDING orders older than UNPAID_ORDER_TTL and release their reserved stock."""
    cutoff = timezone.now() - UNPAID_ORDER_TTL
    stale = Order.objects.filter(status=Order.OrderStatus.PENDING, created_at__lt=cutoff)
    cancelled = 0
    for order in stale:
        try:
            with transaction.atomic():
                locked = Order.objects.select_for_update().get(id=order.id)
                if locked.status != Order.OrderStatus.PENDING:
                    continue
                locked.transition_to(Order.OrderStatus.CANCELLED)
                cancelled += 1
        except Exception:
            logger.exception('Failed to cancel expired order %s', order.id)

    # Expire abandoned anonymous carts (no user) older than 7 days
    from apps.cart.models import Cart
    cart_cutoff = timezone.now() - timedelta(days=7)
    Cart.objects.filter(user__isnull=True, updated_at__lt=cart_cutoff).delete()

    return cancelled


@shared_task
def send_order_receipt_email(order_id: str) -> bool:
    """Send a multipart order receipt email via the configured backend."""
    try:
        order = Order.objects.select_related('user').prefetch_related('items').get(id=order_id)
    except Order.DoesNotExist:
        return False
    context = _order_email_context(order)
    try:
        _send_templated_email(
            subject=f'GASH E-COM: Order {order.order_number} receipt',
            text_template='emails/order_receipt.txt',
            html_template='emails/order_receipt.html',
            context=context,
            recipients=[order.user.email],
        )
    except Exception:
        return False
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
    from apps.users.models import User

    low_items = list(
        Inventory.objects.select_related('product', 'product__seller')
        .filter(quantity_available__lte=F('low_stock_threshold'), low_stock_alerted=False)
    )
    if not low_items:
        return 0

    admin_emails = list(
        User.objects.filter(role=User.Role.ADMIN, is_active=True, is_suspended=False)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    recipients_by_email: dict[str, list] = {}
    for inv in low_items:
        recipients = set(admin_emails)
        seller = getattr(inv.product, 'seller', None)
        if seller is not None and seller.email:
            recipients.add(seller.email)
        if not recipients:
            recipients.add(settings.DEFAULT_FROM_EMAIL)
        for email in recipients:
            recipients_by_email.setdefault(email, []).append(inv)

    notified_ids = set()
    for email, items in recipients_by_email.items():
        context = {
            'items': [
                {
                    'name': inv.product.name,
                    'sku': inv.sku,
                    'quantity': inv.quantity_available,
                    'threshold': inv.low_stock_threshold,
                }
                for inv in items
            ],
            'frontend_url': settings.FRONTEND_URL.rstrip('/'),
        }
        try:
            _send_templated_email(
                subject='GASH E-COM low-stock alert',
                text_template='emails/low_stock.txt',
                html_template='emails/low_stock.html',
                context=context,
                recipients=[email],
            )
            notified_ids.update(inv.id for inv in items)
        except Exception:
            pass

    if notified_ids:
        Inventory.objects.filter(id__in=notified_ids).update(low_stock_alerted=True)
    return len(notified_ids)


@shared_task
def send_order_shipping_email(order_id: str) -> bool:
    try:
        order = Order.objects.select_related('user').prefetch_related('items').get(id=order_id)
    except Order.DoesNotExist:
        return False
    try:
        _send_templated_email(
            subject=f'GASH E-COM: Your order {order.order_number} has shipped',
            text_template='emails/order_shipped.txt',
            html_template='emails/order_shipped.html',
            context=_order_email_context(order),
            recipients=[order.user.email],
        )
    except Exception:
        return False
    return True
