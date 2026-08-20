import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDModel
from apps.common.uploads import safe_extension

from .managers import UserManager


def avatar_upload_to(instance, filename: str) -> str:
    # Kengaytma oq ro'yxatdan olinadi — `.html`/`.svg` kabi fayllar media
    # papkasiga tushib, API domenida skript sifatida ochilib ketmasligi uchun.
    return f"avatars/{instance.pk}.{safe_extension(filename)}"


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    """TZ dagi `profiles` jadvali.

    Django'ning auth tizimi bilan bitta jadvalda birlashtirilgan — shu tufayli
    `request.user` to'g'ridan-to'g'ri rol va telefonni biladi, ortiqcha JOIN yo'q.
    """

    class Role(models.TextChoices):
        CLIENT = "client", "Mijoz"
        BARBER = "barber", "Usta"
        SUPERADMIN = "superadmin", "Super admin"

    phone = models.CharField("telefon", max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField("email", unique=True, null=True, blank=True)
    full_name = models.CharField("F.I.SH.", max_length=150, blank=True)
    role = models.CharField("rol", max_length=16, choices=Role.choices, default=Role.CLIENT, db_index=True)
    avatar = models.ImageField("avatar", upload_to=avatar_upload_to, blank=True, null=True)

    is_phone_verified = models.BooleanField("telefon tasdiqlangan", default=False)
    google_sub = models.CharField("Google sub", max_length=64, unique=True, null=True, blank=True)

    is_active = models.BooleanField("faol", default=True)
    is_staff = models.BooleanField("xodim", default=False)

    created_at = models.DateTimeField("ro'yxatdan o'tgan", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("yangilangan", auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "profiles"
        verbose_name = "foydalanuvchi"
        verbose_name_plural = "foydalanuvchilar"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.full_name or self.phone or self.email or str(self.id)

    # ── qulaylik xossalari ────────────────────────────────────────────
    @property
    def is_client(self) -> bool:
        return self.role == self.Role.CLIENT

    @property
    def is_barber(self) -> bool:
        return self.role == self.Role.BARBER

    @property
    def is_superadmin(self) -> bool:
        return self.role == self.Role.SUPERADMIN or self.is_superuser

    @property
    def display_name(self) -> str:
        return self.full_name or (self.phone or "")


class OTPPurpose(models.TextChoices):
    LOGIN = "login", "Kirish"
    PHONE_CHANGE = "phone_change", "Raqam almashtirish"


class PhoneOTP(UUIDModel):
    """SMS orqali yuborilgan bir martalik kod.

    Kodning o'zi saqlanmaydi — faqat SHA-256 hash (baza sizib chiqsa ham kod bilinmaydi).
    """

    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices, default=OTPPurpose.LOGIN)

    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "phone_otps"
        verbose_name = "SMS kod"
        verbose_name_plural = "SMS kodlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["phone", "is_used", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.phone} ({self.created_at:%H:%M})"

    # ── yordamchilar ──────────────────────────────────────────────────
    @staticmethod
    def hash_code(code: str) -> str:
        salted = f"{settings.SECRET_KEY}:{code}".encode()
        return hashlib.sha256(salted).hexdigest()

    @classmethod
    def generate_code(cls, phone: str) -> str:
        # ⚠️ Test raqamlari FAQAT DEBUG rejimida qat'iy kod oladi. Aks holda
        # prodda `.env` da qolib ketgan bitta raqam butun autentifikatsiyani ochib
        # yuborardi — kimdir raqamni bilsa, doimiy kod bilan kirib olardi.
        if settings.DEBUG and phone in settings.OTP_TEST_PHONES:
            return settings.OTP_DEBUG_CODE
        length = settings.OTP_LENGTH
        return "".join(secrets.choice("0123456789") for _ in range(length))

    @classmethod
    def issue(cls, phone: str, purpose: str = OTPPurpose.LOGIN) -> tuple["PhoneOTP", str]:
        """Eski kodlarni bekor qilib, yangisini yaratadi."""
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)
        code = cls.generate_code(phone)
        otp = cls.objects.create(
            phone=phone,
            purpose=purpose,
            code_hash=cls.hash_code(code),
            expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        )
        return otp, code

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def seconds_left(self) -> int:
        return max(0, int((self.expires_at - timezone.now()).total_seconds()))

    def check_code(self, code: str) -> bool:
        return secrets.compare_digest(self.code_hash, self.hash_code(code))

    def mark_used(self) -> None:
        self.is_used = True
        self.save(update_fields=["is_used"])
