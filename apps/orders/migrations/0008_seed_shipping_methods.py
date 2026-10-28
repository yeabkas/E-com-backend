from decimal import Decimal

from django.db import migrations


def seed_shipping(apps, schema_editor):
    ShippingMethod = apps.get_model('orders', 'ShippingMethod')
    ShippingMethod.objects.get_or_create(
        name='Standard Delivery',
        defaults={'price': Decimal('50.00'), 'free_over_threshold': Decimal('1000.00')},
    )
    ShippingMethod.objects.get_or_create(
        name='Express Delivery',
        defaults={'price': Decimal('150.00'), 'free_over_threshold': None},
    )


def unseed_shipping(apps, schema_editor):
    ShippingMethod = apps.get_model('orders', 'ShippingMethod')
    ShippingMethod.objects.filter(
        name__in=['Standard Delivery', 'Express Delivery'],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0007_orderstatushistory'),
    ]

    operations = [
        migrations.RunPython(seed_shipping, unseed_shipping),
    ]
