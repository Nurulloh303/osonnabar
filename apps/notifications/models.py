from django.conf import settings
from django.db import models

from apps.common.models import UUIDModel


class PushSubscription(UUIDModel):
    """Brauzer/qurilma obunasi (Web Push).

    Bitta foydalanuvchi bir nechta qurilmadan kirishi mumkin — telefon, noutbuk,
    ish kompyuteri. Har biri alohida `endpoint` beradi, shuning uchun bitta
    `user` ga bir nechta yozuv ulanadi.

    `endpoint` — unikal: brauzer qayta obuna bo'lganda yangi yozuv yaratilmaydi,
    borini yangilaymiz. Boshqa foydalanuvchi shu brauzerda kirsa, obuna unga
    o'tadi (aks holda eski egasiga begona qurilmaga xabar ketardi).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    #: Push xizmatining (FCM / Mozilla / Apple) manzili. URL uzun bo'lishi mumkin.
    endpoint = models.TextField("endpoint", unique=True)
    #: Brauzer bergan `{"p256dh": "...", "auth": "..."}` — shifrlash kalitlari.
    auth_keys = models.JSONField("kalitlar")

    user_agent = models.CharField("qurilma", max_length=255, blank=True)

    created_at = models.DateTimeField("qo'shilgan", auto_now_add=True)
    last_success_at = models.DateTimeField("oxirgi muvaffaqiyatli yuborish", null=True, blank=True)

    class Meta:
        db_table = "push_subscriptions"
        verbose_name = "push obuna"
        verbose_name_plural = "push obunalar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.endpoint[:40]}…"

    @property
    def as_subscription_info(self) -> dict:
        """`pywebpush` kutadigan format."""
        return {"endpoint": self.endpoint, "keys": self.auth_keys}


class NotificationKind(models.TextChoices):
    BOOKING_CONFIRMED = "booking_confirmed", "Navbat tasdiqlandi"
    BOOKING_CANCELLED = "booking_cancelled", "Navbat bekor qilindi"
    BOOKING_COMPLETED = "booking_completed", "Navbat yakunlandi"
    BOOKING_REMINDER = "booking_reminder", "Navbat eslatmasi"
    BOOKING_CREATED = "booking_created", "Yangi navbat"
    SYSTEM = "system", "Tizim xabari"


class Notification(UUIDModel):
    """Sayt ichidagi qo'ng'iroqcha uchun xabar tarixi.

    Push yuborilmasa ham (foydalanuvchi ruxsat bermagan, VAPID sozlanmagan,
    push xizmati javob bermadi) bu yozuv baribir yaratiladi — shuning uchun
    qo'ng'iroqcha har doim to'liq tarixni ko'rsatadi.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="foydalanuvchi",
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    title = models.CharField("sarlavha", max_length=200)
    body = models.TextField("matn", max_length=1000)
    kind = models.CharField(
        "turi", max_length=32, choices=NotificationKind.choices, default=NotificationKind.SYSTEM
    )
    #: Front xabarni bosganda qayerga o'tishi ("/bookings/<id>" kabi).
    url = models.CharField("havola", max_length=255, blank=True)

    # `bookings.Booking` ga satr orqali havola — modullar aylanma import qilmasligi uchun.
    booking = models.ForeignKey(
        "bookings.Booking",
        verbose_name="navbat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    is_read = models.BooleanField("o'qilgan", default=False, db_index=True)
    created_at = models.DateTimeField("yaratilgan", auto_now_add=True, db_index=True)

    #: Push haqiqatan yuborilganmi. `null` — hali urinilmagan yoki muvaffaqiyatsiz.
    push_sent_at = models.DateTimeField("push yuborilgan", null=True, blank=True)

    class Meta:
        db_table = "notifications"
        verbose_name = "xabarnoma"
        verbose_name_plural = "xabarnomalar"
        ordering = ("-created_at",)
        indexes = [
            # Qo'ng'iroqcha ro'yxati va o'qilmaganlar sanog'i — eng ko'p ishlatiladigan ikkita so'rov.
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} · {self.title}"
