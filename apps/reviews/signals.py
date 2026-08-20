"""Sharh o'zgarganda usta va salon reytingini qayta hisoblash."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Review


@receiver([post_save, post_delete], sender=Review)
def refresh_rating(sender, instance: Review, **kwargs):
    instance.barber.recalculate_rating()
