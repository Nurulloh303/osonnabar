from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.salons.models import Barber, Salon


class BookingStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    CONFIRMED = "confirmed", "Tasdiqlangan"
    COMPLETED = "completed", "Yakunlangan"
    CANCELLED = "cancelled", "Bekor qilingan"


#: Vaqtni band qiladigan holatlar — slot to'qnashuvi shular bo'yicha tekshiriladi
ACTIVE_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED)


class Booking(BaseModel):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="mijoz", on_delete=models.CASCADE, related_name="bookings"
    )
    barber = models.ForeignKey(Barber, verbose_name="usta", on_delete=models.CASCADE, related_name="bookings")
    salon = models.ForeignKey(
        Salon, verbose_name="salon", on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
    )

    booking_date = models.DateField("sana", db_index=True)
    booking_time = models.TimeField("vaqt")
    duration_minutes = models.PositiveSmallIntegerField("davomiyligi (daqiqa)", default=30)

    service_name = models.CharField("xizmat", max_length=100)
    price = models.PositiveIntegerField("narx (so'm)", default=0)

    status = models.CharField(
        "holat", max_length=16, choices=BookingStatus.choices, default=BookingStatus.PENDING, db_index=True
    )
    client_note = models.CharField("mijoz izohi", max_length=500, blank=True)

    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    cancel_reason = models.CharField("bekor qilish sababi", max_length=255, blank=True)

    #: Eslatma yuborilgan vaqt. Cron oynasi bir-birining ustiga tushganda
    #: bitta navbatga ikkinchi marta eslatma ketmasligi uchun.
    reminder_sent_at = models.DateTimeField("eslatma yuborilgan", null=True, blank=True)

    class Meta:
        db_table = "bookings"
        verbose_name = "navbat"
        verbose_name_plural = "navbatlar"
        ordering = ("-booking_date", "-booking_time")
        indexes = [
            models.Index(fields=["barber", "booking_date", "status"]),
            models.Index(fields=["client", "-booking_date"]),
            models.Index(fields=["status", "booking_date"]),
        ]
        constraints = [
            # ⚠️ Asosiy himoya: bitta ustada bitta vaqtga faqat bitta faol bron.
            # Bu qisman unikal indeks (partial unique index) — bekor qilingan bronlar hisobga olinmaydi.
            models.UniqueConstraint(
                fields=["barber", "booking_date", "booking_time"],
                condition=~models.Q(status=BookingStatus.CANCELLED),
                name="uniq_active_booking_slot",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.booking_date} {self.booking_time:%H:%M} · {self.service_name}"

    # ── hisoblanadigan xossalar ───────────────────────────────────────
    @property
    def starts_at(self) -> datetime:
        naive = datetime.combine(self.booking_date, self.booking_time)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def is_active(self) -> bool:
        return self.status in (BookingStatus.PENDING, BookingStatus.CONFIRMED)

    @property
    def is_past(self) -> bool:
        return self.ends_at < timezone.now()

    def can_be_cancelled_by_client(self) -> tuple[bool, str]:
        if not self.is_active:
            return False, "Bu navbatni bekor qilib bo'lmaydi."
        window = timedelta(minutes=settings.BOOKING_CANCEL_WINDOW_MINUTES)
        if self.starts_at - timezone.now() < window:
            return False, (
                f"Navbat boshlanishiga {settings.BOOKING_CANCEL_WINDOW_MINUTES} daqiqadan kam vaqt qoldi. "
                "Ustaga qo'ng'iroq qiling."
            )
        return True, ""
