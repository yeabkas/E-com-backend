import logging
import threading

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Category, Product, ProductImage

logger = logging.getLogger(__name__)


def _post_revalidation(tags):
    try:
        response = requests.post(
            settings.FRONTEND_REVALIDATE_URL,
            json={'tags': sorted(set(tags))},
            headers={'Authorization': f'Bearer {settings.FRONTEND_REVALIDATE_SECRET}'},
            timeout=3,
        )
        if response.status_code >= 400:
            logger.warning('Frontend revalidation failed: %s %s', response.status_code, response.text[:200])
    except requests.RequestException as exc:
        logger.warning('Frontend revalidation request failed: %s', exc)


def revalidate_frontend(tags):
    """Ask the Next.js app to refresh its cached catalog data after a commit."""
    cache.delete('catalog:categories:v1')
    if not settings.FRONTEND_REVALIDATE_SECRET:
        return
    transaction.on_commit(
        lambda: threading.Thread(
            target=_post_revalidation,
            args=(tags,),
            daemon=True,
        ).start()
    )


@receiver([post_save, post_delete], sender=Product, dispatch_uid='catalog.revalidate_product')
def product_changed(sender, instance, **kwargs):
    tags = ['products']
    if instance.slug:
        tags.append(f'product:{instance.slug}')
    revalidate_frontend(tags)


@receiver([post_save, post_delete], sender=Category, dispatch_uid='catalog.revalidate_category')
def category_changed(sender, instance, **kwargs):
    revalidate_frontend(['categories', 'products'])


@receiver([post_save, post_delete], sender=ProductImage, dispatch_uid='catalog.revalidate_image')
def product_image_changed(sender, instance, **kwargs):
    tags = ['products']
    slug = Product.objects.filter(pk=instance.product_id).values_list('slug', flat=True).first()
    if slug:
        tags.append(f'product:{slug}')
    revalidate_frontend(tags)
