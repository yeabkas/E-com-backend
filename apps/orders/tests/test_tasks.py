import pytest
from datetime import timedelta
from django.core import mail
from django.utils import timezone

from apps.catalog.models import Inventory
from apps.catalog.tests.factories import CategoryFactory, InventoryFactory, ProductFactory
from apps.orders.models import Order, OrderItem
from apps.orders.tasks import expire_unpaid_orders, send_low_stock_alerts
from apps.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestLowStockAlerts:
    def setup_method(self):
        self.admin = UserFactory(role='ADMIN', email='admin@example.com')
        self.seller = UserFactory(role='SELLER', email='seller@example.com')
        self.category = CategoryFactory(name='Alerts', slug='alerts')
        self.product = ProductFactory(
            name='Low Stock Widget', seller=self.seller, category=self.category
        )
        self.inventory = InventoryFactory(
            product=self.product,
            sku='LOW-1',
            quantity_available=1,
            low_stock_threshold=2,
        )

    def test_low_stock_alerts_go_to_admins_and_seller_once(self):
        count = send_low_stock_alerts()
        assert count == 1
        assert len(mail.outbox) == 2
        recipients = {address for message in mail.outbox for address in message.to}
        assert recipients == {'admin@example.com', 'seller@example.com'}
        assert all('low-stock' in message.subject for message in mail.outbox)
        assert all('Low Stock Widget' in message.body for message in mail.outbox)

        self.inventory.refresh_from_db()
        assert self.inventory.low_stock_alerted is True

        assert send_low_stock_alerts() == 0
        assert len(mail.outbox) == 2

    def test_replenishing_stock_clears_the_alert_flag(self):
        send_low_stock_alerts()
        self.inventory.refresh_from_db()
        assert self.inventory.low_stock_alerted is True

        self.inventory.quantity_available = 10
        self.inventory.save(update_fields=['quantity_available'])
        self.inventory.refresh_from_db()
        assert self.inventory.low_stock_alerted is False

        assert send_low_stock_alerts() == 0
        mail.outbox.clear()
        assert len(mail.outbox) == 0

    def test_expired_orders_release_stock_once(self):
        buyer = UserFactory(role='CUSTOMER')
        self.inventory.quantity_available = 5
        self.inventory.quantity_reserved = 2
        self.inventory.save()
        order = Order.objects.create(
            user=buyer,
            status=Order.OrderStatus.PENDING,
            subtotal=20,
            total_amount=20,
        )
        OrderItem.objects.create(
            order=order,
            product_id=self.product.id,
            product_name=self.product.name,
            sku=self.inventory.sku,
            quantity=2,
            unit_price=10,
        )
        Order.objects.filter(id=order.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )

        assert expire_unpaid_orders() == 1
        order.refresh_from_db()
        self.inventory.refresh_from_db()
        assert order.status == Order.OrderStatus.CANCELLED
        assert self.inventory.quantity_available == 7
        assert self.inventory.quantity_reserved == 0
        assert list(order.status_history.values_list('status', flat=True)) == ['CANCELLED']

        # Running the sweep again must not release the same stock twice.
        assert expire_unpaid_orders() == 0
        self.inventory.refresh_from_db()
        assert self.inventory.quantity_available == 7
