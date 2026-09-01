from django.conf import settings
from rest_framework import serializers

from apps.common.uploads import validate_image_upload

from .models import User
from .validators import normalize_phone


class UserSerializer(serializers.ModelSerializer):
    """`/auth/me/` va barcha nested foydalanuvchi javoblari uchun."""

    barber_id = serializers.SerializerMethodField()
    is_profile_complete = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone",
            "email",
            "full_name",
            "role",
            "avatar",
            "is_phone_verified",
            "is_active",
            "barber_id",
            "is_profile_complete",
            "created_at",
        )
        read_only_fields = ("id", "phone", "email", "role", "is_phone_verified", "is_active", "created_at")

    def get_barber_id(self, obj) -> str | None:
        barber = getattr(obj, "barber", None)
        return str(barber.id) if barber else None

    def get_is_profile_complete(self, obj) -> bool:
        return bool(obj.full_name.strip())


class AvatarUploadSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=True, validators=[validate_image_upload])

    class Meta:
        model = User
        fields = ("avatar",)


class PhoneField(serializers.CharField):
    def to_internal_value(self, data):
        return normalize_phone(super().to_internal_value(data))


# ── OTP ──────────────────────────────────────────────────────────────────
class OTPRequestSerializer(serializers.Serializer):
    phone = PhoneField(help_text="+998901234567 / 901234567 — istalgan format")


class OTPRequestResponseSerializer(serializers.Serializer):
    phone = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Kod amal qilish muddati (sekund)")
    resend_after = serializers.IntegerField(help_text="Qayta yuborishga ruxsat etiladigan vaqt (sekund)")
    is_new_user = serializers.BooleanField()
    code = serializers.CharField(required=False, help_text="Faqat DEBUG rejimida qaytariladi")


class OTPVerifySerializer(serializers.Serializer):
    phone = PhoneField()
    code = serializers.CharField(min_length=4, max_length=8, trim_whitespace=True)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Kod faqat raqamlardan iborat bo'lishi kerak.")
        if len(value) != settings.OTP_LENGTH:
            raise serializers.ValidationError(f"Kod {settings.OTP_LENGTH} xonali bo'lishi kerak.")
        return value


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(help_text="Google Sign-In dan olingan `credential` (JWT)")


class AuthMethodsSerializer(serializers.Serializer):
    google = serializers.BooleanField(help_text="Google tugmasi ko'rsatilsinmi")
    google_client_id = serializers.CharField(help_text="Google Sign-In uchun `client_id`")
    sms = serializers.BooleanField(help_text="Telefon + SMS kod orqali kirish yoqilganmi")


class AuthResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    is_new_user = serializers.BooleanField()
    access = serializers.CharField(
        required=False,
        help_text="Faqat `?with_tokens=1` bo'lganda (mobil ilova / Swagger uchun). "
        "Brauzerda tokenlar httpOnly cookie'ga yoziladi.",
    )
    refresh = serializers.CharField(required=False)


class MessageSerializer(serializers.Serializer):
    detail = serializers.CharField()
