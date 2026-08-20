from datetime import time as dt_time

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import BaseModel


class Specialty(models.TextChoices):
    MEN = "men", "Erkaklar"
    WOMEN = "women", "Ayollar"
    KIDS = "kids", "Bolalar"
    UNISEX = "unisex", "Aralash"


class Salon(BaseModel):
    """Muassasa (sartaroshxona / go'zallik saloni). Xaritada shu nuqta ko'rsatiladi."""

    name = models.CharField("nomi", max_length=150, db_index=True)
    description = models.TextField("tavsif", blank=True)
    specialty = models.CharField(
        "yo'nalish", max_length=16, choices=Specialty.choices, default=Specialty.UNISEX, db_index=True
    )

    address = models.CharField("manzil", max_length=255, blank=True)
    district = models.CharField("tuman", max_length=100, blank=True, db_index=True)
    city = models.CharField("shahar", max_length=100, default="Toshkent", db_index=True)
    location_lat = models.FloatField("kenglik (lat)", db_index=True)
    location_lng = models.FloatField("uzunlik (lng)", db_index=True)

    phone = models.CharField("telefon", max_length=20, blank=True)
    cover_image = models.ImageField("muqova rasmi", upload_to="salons/", blank=True, null=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="egasi",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_salons",
    )
    is_active = models.BooleanField("faol", default=True, db_index=True)

    # Denormalizatsiya — ro'yxatni reyting bo'yicha saralashda JOIN/agregatsiya qilmaslik uchun
    rating_avg = models.FloatField("o'rtacha reyting", default=0)
    reviews_count = models.PositiveIntegerField("sharhlar soni", default=0)

    class Meta:
        db_table = "salons"
        verbose_name = "salon"
        verbose_name_plural = "salonlar"
        ordering = ("-rating_avg", "name")
        indexes = [models.Index(fields=["location_lat", "location_lng"])]

    def __str__(self) -> str:
        return self.name

    def recalculate_rating(self) -> None:
        from django.db.models import Avg, Count

        agg = self.reviews.aggregate(avg=Avg("rating"), cnt=Count("id"))
        Salon.objects.filter(pk=self.pk).update(
            rating_avg=round(agg["avg"] or 0, 2), reviews_count=agg["cnt"] or 0
        )


class Barber(BaseModel):
    """Usta. `profile` — TZ dagi `profiles.id` ga foreign key."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        BLOCKED = "blocked", "Bloklangan"

    profile = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="profil",
        on_delete=models.CASCADE,
        related_name="barber",
    )
    salon = models.ForeignKey(
        Salon,
        verbose_name="salon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="barbers",
    )

    specialty = models.CharField(
        "mutaxassislik", max_length=16, choices=Specialty.choices, default=Specialty.MEN, db_index=True
    )
    status = models.CharField(
        "holat", max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    bio = models.TextField("o'zi haqida", blank=True)
    experience_years = models.PositiveSmallIntegerField("tajriba (yil)", default=0)
    avatar = models.ImageField("rasm", upload_to="barbers/", blank=True, null=True)

    # Salon ichida bo'lsa ham, usta alohida nuqtada ishlashi mumkin (uyda, ko'chma xizmat)
    location_lat = models.FloatField("kenglik (lat)", null=True, blank=True, db_index=True)
    location_lng = models.FloatField("uzunlik (lng)", null=True, blank=True, db_index=True)

    #  [{"name": "Soch olish", "price": 50000, "duration_minutes": 30}, ...]
    #  Narx SERVER tomonda shu ro'yxatdan olinadi — mijoz o'zi narx yubora olmaydi.
    services = models.JSONField("xizmatlar", default=list, blank=True)

    default_slot_minutes = models.PositiveSmallIntegerField(
        "standart slot (daqiqa)", default=30, validators=[MinValueValidator(10), MaxValueValidator(240)]
    )

    rating_avg = models.FloatField("o'rtacha reyting", default=0)
    reviews_count = models.PositiveIntegerField("sharhlar soni", default=0)
    completed_bookings = models.PositiveIntegerField("bajarilgan navbatlar", default=0)

    class Meta:
        db_table = "barbers"
        verbose_name = "usta"
        verbose_name_plural = "ustalar"
        ordering = ("-rating_avg", "-completed_bookings")
        indexes = [models.Index(fields=["status", "specialty"])]

    def __str__(self) -> str:
        return f"{self.profile.display_name} ({self.get_specialty_display()})"

    # ── koordinata: o'ziniki bo'lmasa salonnikini oladi ────────────────
    @property
    def lat(self) -> float | None:
        return self.location_lat if self.location_lat is not None else getattr(self.salon, "location_lat", None)

    @property
    def lng(self) -> float | None:
        return self.location_lng if self.location_lng is not None else getattr(self.salon, "location_lng", None)

    @property
    def is_bookable(self) -> bool:
        return self.status == self.Status.ACTIVE and self.profile.is_active

    def find_service(self, name: str) -> dict | None:
        """Xizmatni nomi bo'yicha topadi (registr farqi hisobga olinmaydi)."""
        target = (name or "").strip().casefold()
        for item in self.services or []:
            if str(item.get("name", "")).strip().casefold() == target:
                return item
        return None

    def recalculate_rating(self) -> None:
        from django.db.models import Avg, Count

        agg = self.reviews.aggregate(avg=Avg("rating"), cnt=Count("id"))
        Barber.objects.filter(pk=self.pk).update(
            rating_avg=round(agg["avg"] or 0, 2), reviews_count=agg["cnt"] or 0
        )
        if self.salon_id:
            self.salon.recalculate_rating()


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Dushanba"
    TUESDAY = 1, "Seshanba"
    WEDNESDAY = 2, "Chorshanba"
    THURSDAY = 3, "Payshanba"
    FRIDAY = 4, "Juma"
    SATURDAY = 5, "Shanba"
    SUNDAY = 6, "Yakshanba"


class BarberSchedule(BaseModel):
    """Ustaning hafta kunlari bo'yicha ish jadvali. Bo'sh slotlar shundan generatsiya qilinadi."""

    barber = models.ForeignKey(Barber, on_delete=models.CASCADE, related_name="schedules")
    weekday = models.PositiveSmallIntegerField("hafta kuni", choices=Weekday.choices)
    is_working = models.BooleanField("ishlaydi", default=True)

    start_time = models.TimeField("ish boshlanishi", default=dt_time(9, 0))
    end_time = models.TimeField("ish tugashi", default=dt_time(20, 0))
    break_start = models.TimeField("tanaffus boshi", null=True, blank=True)
    break_end = models.TimeField("tanaffus oxiri", null=True, blank=True)

    slot_minutes = models.PositiveSmallIntegerField(
        "slot uzunligi (daqiqa)", default=30, validators=[MinValueValidator(10), MaxValueValidator(240)]
    )

    class Meta:
        db_table = "barber_schedules"
        verbose_name = "ish jadvali"
        verbose_name_plural = "ish jadvallari"
        ordering = ("barber", "weekday")
        constraints = [
            models.UniqueConstraint(fields=["barber", "weekday"], name="uniq_barber_weekday"),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="schedule_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.barber_id} · {self.get_weekday_display()}"


class BarberDayOff(BaseModel):
    """Aniq sanadagi dam olish / ta'til — jadvaldan ustun turadi."""

    barber = models.ForeignKey(Barber, on_delete=models.CASCADE, related_name="days_off")
    date = models.DateField("sana", db_index=True)
    reason = models.CharField("sabab", max_length=255, blank=True)

    class Meta:
        db_table = "barber_days_off"
        verbose_name = "dam olish kuni"
        verbose_name_plural = "dam olish kunlari"
        ordering = ("-date",)
        constraints = [models.UniqueConstraint(fields=["barber", "date"], name="uniq_barber_dayoff")]

    def __str__(self) -> str:
        return f"{self.barber_id} · {self.date}"
