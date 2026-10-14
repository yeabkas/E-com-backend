from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.payments.provider import get_provider


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
        callback_url = request.data.get(
            'callback_url',
            f"{request.scheme}://{request.get_host()}/api/v1/payments/webhooks/chapa/",
        )
        try:
            result = provider.initialize(order, callback_url=callback_url)
        except RuntimeError as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

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
        if not tx_ref:
            return Response({'error': 'tx_ref is required'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider()
        result = provider.verify(tx_ref)
        if result['ok']:
            if order.status == Order.OrderStatus.PENDING:
                order.transition_to(Order.OrderStatus.PAID)
                try:
                    from apps.orders.tasks import send_order_receipt_email
                    send_order_receipt_email.delay(str(order.id))
                except Exception:
                    pass
            return Response({'paid': True, 'status': order.status, 'order_id': str(order.id)})
        return Response({'paid': False, 'status': order.status, 'detail': result['raw']}, status=status.HTTP_400_BAD_REQUEST)


class ChapaWebhookView(APIView):
    """POST /api/v1/payments/webhooks/chapa/ — vendor server-to-server notification."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        tx_ref = request.data.get('tx_ref')
        if not tx_ref:
            return Response({'error': 'tx_ref is required'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider()
        result = provider.verify(tx_ref)
        try:
            order = Order.objects.get(chapa_tx_ref=tx_ref)
        except Order.DoesNotExist:
            return Response({'error': 'unknown tx_ref'}, status=status.HTTP_404_NOT_FOUND)

        if result['ok'] and order.status == Order.OrderStatus.PENDING:
            order.transition_to(Order.OrderStatus.PAID)
            try:
                from apps.orders.tasks import send_order_receipt_email
                send_order_receipt_email.delay(str(order.id))
            except Exception:
                pass
        return Response({'received': True, 'status': order.status})
