from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import logging

from django.conf import settings
from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.payments.provider import get_provider

logger = logging.getLogger(__name__)


def _transition_pending_to_paid(order_id, expected_ref=None):
    """Lock and pay an order exactly once. Returns (order, changed)."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        if expected_ref and order.chapa_tx_ref != expected_ref:
            raise Order.DoesNotExist
        if order.status != Order.OrderStatus.PENDING:
            return order, False
        order.transition_to(Order.OrderStatus.PAID)
        return order, True


def _send_receipt(order_id):
    try:
        from apps.orders.tasks import send_order_receipt_email
        send_order_receipt_email.delay(str(order_id))
    except Exception:
        pass


class ChapaInitView(APIView):
    """POST /api/v1/payments/chapa/init/ {order_id} -> redirect URL for Chapa checkout."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except (Order.DoesNotExist, ValueError):
            raise Http404('Order not found')

        if order.status != Order.OrderStatus.PENDING:
            return Response({'error': f'Order is not payable (status {order.status})'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider()
        callback_url = f"{settings.BACKEND_URL.rstrip('/')}/api/v1/payments/webhooks/chapa/"
        tx_ref = order.chapa_tx_ref or f"gash_{order.id.hex[:12]}"
        if order.chapa_tx_ref != tx_ref:
            order.chapa_tx_ref = tx_ref
            order.save(update_fields=['chapa_tx_ref', 'updated_at'])
        return_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}/checkout/success/{order.id}"
            f"?tx_ref={tx_ref}"
        )
        try:
            result = provider.initialize(
                order,
                callback_url=callback_url,
                return_url=return_url,
                tx_ref=tx_ref,
            )
        except RuntimeError as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        if order.chapa_tx_ref != result['tx_ref']:
            order.chapa_tx_ref = result['tx_ref']
            order.save(update_fields=['chapa_tx_ref', 'updated_at'])
        return Response({'checkout_url': result['checkout_url'], 'tx_ref': result['tx_ref']})


class ChapaVerifyView(APIView):
    """POST /api/v1/payments/chapa/verify/ {order_id} -> confirms payment server-side."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get('order_id')
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except (Order.DoesNotExist, ValueError):
            raise Http404('Order not found')

        tx_ref = request.data.get('tx_ref') or order.chapa_tx_ref
        if not tx_ref or not order.chapa_tx_ref or tx_ref != order.chapa_tx_ref:
            return Response({'error': 'Unknown payment reference for this order.'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider()
        result = provider.verify(tx_ref)
        if not result['ok']:
            return Response({'paid': False, 'status': order.status, 'detail': result['raw']}, status=status.HTTP_400_BAD_REQUEST)
        if not payment_matches_order(result, order):
            return Response({'error': 'Verified payment amount or currency does not match this order.'}, status=status.HTTP_400_BAD_REQUEST)
        if order.status == Order.OrderStatus.CANCELLED:
            logger.critical(
                'Late Chapa payment for cancelled order %s (tx_ref=%s)', order.id, tx_ref
            )
            return Response(
                {
                    'paid': True,
                    'status': order.status,
                    'error': 'Payment succeeded after this order was cancelled. Contact support for a refund.',
                },
                status=status.HTTP_409_CONFLICT,
            )
        order, changed = _transition_pending_to_paid(order.id, expected_ref=tx_ref)
        if changed:
            _send_receipt(order.id)
        return Response({'paid': True, 'status': order.status, 'order_id': str(order.id)})


class ChapaWebhookView(APIView):
    """POST /api/v1/payments/webhooks/chapa/ — vendor server-to-server notification."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = getattr(settings, 'CHAPA_WEBHOOK_SECRET', '')
        if secret and not self._signature_matches(request, secret):
            return Response({'error': 'invalid webhook signature'}, status=status.HTTP_401_UNAUTHORIZED)

        tx_ref = request.data.get('tx_ref')
        if not tx_ref:
            return Response({'error': 'tx_ref is required'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider()
        result = provider.verify(tx_ref)
        try:
            order = Order.objects.get(chapa_tx_ref=tx_ref)
        except Order.DoesNotExist:
            return Response({'error': 'unknown tx_ref'}, status=status.HTTP_404_NOT_FOUND)

        if result['ok'] and payment_matches_order(result, order):
            if order.status == Order.OrderStatus.CANCELLED:
                logger.critical(
                    'Late Chapa webhook payment for cancelled order %s (tx_ref=%s)',
                    order.id,
                    tx_ref,
                )
                return Response({
                    'received': True,
                    'status': order.status,
                    'warning': 'Payment received for a cancelled order; manual refund required.',
                })
            order, changed = _transition_pending_to_paid(order.id, expected_ref=tx_ref)
            if changed:
                _send_receipt(order.id)
        return Response({'received': True, 'status': order.status})

    @staticmethod
    def _signature_matches(request, secret: str) -> bool:
        secret_bytes = secret.encode('utf-8')
        payload_signature = hmac.new(secret_bytes, request.body, hashlib.sha256).hexdigest()
        secret_signature = hmac.new(secret_bytes, secret_bytes, hashlib.sha256).hexdigest()
        candidates = {
            request.headers.get('x-chapa-signature', ''),
            request.headers.get('chapa-signature', ''),
        }
        return any(
            candidate and hmac.compare_digest(candidate, expected)
            for candidate in candidates
            for expected in (payload_signature, secret_signature)
        )


def payment_matches_order(result, order) -> bool:
    """Validate the verified amount/currency against the order snapshot."""
    try:
        paid_amount = Decimal(str(result.get('amount')))
    except (InvalidOperation, TypeError, ValueError):
        return False
    currency = (result.get('currency') or '').upper()
    if currency != 'ETB':
        return False
    return paid_amount == Decimal(str(order.total_amount))
