from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.bookings.models import Booking
from apps.common.models import BaseModel
from apps.salons.models import Barber, Salon


class Review(BaseModel):
    """Sharh faqat YAKUNLANGAN bron uchun va bron egasi tomonidan yoziladi.

    `booking` — OneToOne, ya'ni bitta xizmatga bitta sharh (soxta reyting qiyinlashadi).
    """

    booking = models.OneToOneField(
        Booking, verbose_name="navbat", on_delete=models.CASCADE, related_name="review"
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="mijoz", on_delete=models.CASCADE, related_name="reviews"
    )
    barber = models.ForeignKey(Barber, verbose_name="usta", on_delete=models.CASCADE, related_name="reviews")
    salon = models.ForeignKey(
        Salon, verbose_name="salon", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )

    rating = models.PositiveSmallIntegerField(
        "baho", validators=[MinValueValidator(1), MaxValueValidator(5)], db_index=True
    )
    comment = models.TextField("izoh", max_length=1000, blank=True)
    barber_reply = models.TextField("usta javobi", max_length=1000, blank=True)

    class Meta:
        db_table = "reviews"
        verbose_name = "sharh"
        verbose_name_plural = "sharhlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["barber", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.barber_id} · {self.rating}★"
