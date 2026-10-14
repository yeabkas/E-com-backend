from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Avg, Count
from .models import Review

@receiver(post_save, sender=Review)
@receiver(post_delete, sender=Review)
def update_product_rating(sender, instance, **kwargs):
    """
    Updates the average_rating and review_count on the Product
    whenever a Review is created, updated, or deleted.
    """
    product = instance.product
    
    # Only count approved reviews
    approved_reviews = Review.objects.filter(product=product, is_approved=True)
    
    aggregates = approved_reviews.aggregate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )
    
    product.average_rating = aggregates['avg_rating'] or 0.00
    product.review_count = aggregates['count'] or 0
    product.save(update_fields=['average_rating', 'review_count'])
