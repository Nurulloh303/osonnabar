from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.accounts.validators import normalize_phone
from apps.common.uploads import validate_image_upload
from apps.salons.models import Barber, Salon
from apps.salons.serializers import ServiceItemSerializer

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    bookings_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.IntegerField(read_only=True)
    barber_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "phone",
            "email",
            "full_name",
            "role",
            "avatar",
            "is_active",
            "is_phone_verified",
            "bookings_count",
            "total_spent",
            "barber_id",
            "created_at",
            "last_login",
        )
        read_only_fields = fields

    def get_barber_id(self, obj) -> str | None:
        barber = getattr(obj, "barber", None)
        return str(barber.id) if barber else None


class AdminBarberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="profile.full_name", read_only=True)
    phone = serializers.CharField(source="profile.phone", read_only=True)
    email = serializers.CharField(source="profile.email", read_only=True)
    is_account_active = serializers.BooleanField(source="profile.is_active", read_only=True)
    salon_name = serializers.CharField(source="salon.name", read_only=True, default=None)
    revenue_total = serializers.IntegerField(read_only=True, default=0)
    bookings_total = serializers.IntegerField(read_only=True, default=0)
    services = ServiceItemSerializer(many=True, required=False)
    avatar = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_upload])

    class Meta:
        model = Barber
        fields = (
            "id",
            "full_name",
            "phone",
            "email",
            "is_account_active",
            "salon",
            "salon_name",
            "specialty",
            "status",
            "bio",
            "experience_years",
            "avatar",
            "location_lat",
            "location_lng",
            "services",
            "default_slot_minutes",
            "rating_avg",
            "reviews_count",
            "completed_bookings",
            "revenue_total",
            "bookings_total",
            "created_at",
        )
        read_only_fields = ("id", "rating_avg", "reviews_count", "completed_bookings", "created_at")


class AdminBarberCreateSerializer(serializers.Serializer):
    """Super admin yangi usta qo'shadi: profil + usta yozuvi bitta so'rovda.

    ⚠️ `email` — MAJBURIY, chunki usta tizimga Google orqali kiradi. U shu
    email bilan Google'da kirganda `GoogleAuthView` mavjud akkauntni topib,
    `google_sub` ni bog'laydi va **usta roli saqlanib qoladi**. Email noto'g'ri
    bo'lsa, usta kirganda unga alohida "mijoz" akkaunti ochilib ketadi.

    `phone` — ixtiyoriy, faqat bog'lanish uchun.
    """

    email = serializers.EmailField(
        help_text="Ustaning Google akkaunti emaili — u shu orqali tizimga kiradi."
    )
    phone = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=150)
    salon = serializers.PrimaryKeyRelatedField(queryset=Salon.objects.all(), required=False, allow_null=True)
    specialty = serializers.ChoiceField(choices=Barber._meta.get_field("specialty").choices, default="men")
    bio = serializers.CharField(required=False, allow_blank=True)
    experience_years = serializers.IntegerField(required=False, min_value=0, max_value=70, default=0)
    location_lat = serializers.FloatField(required=False, allow_null=True)
    location_lng = serializers.FloatField(required=False, allow_null=True)
    services = ServiceItemSerializer(many=True, required=False)
    default_slot_minutes = serializers.IntegerField(required=False, min_value=10, max_value=240, default=30)

    def validate_email(self, value):
        email = value.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user and hasattr(user, "barber"):
            raise serializers.ValidationError("Bu email allaqachon usta sifatida ro'yxatdan o'tgan.")
        return email

    def validate_phone(self, value):
        if not value or not value.strip():
            return ""
        phone = normalize_phone(value)
        user = User.objects.filter(phone=phone).first()
        if user and hasattr(user, "barber"):
            raise serializers.ValidationError("Bu raqam allaqachon usta sifatida ro'yxatdan o'tgan.")
        return phone

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data.pop("email")
        phone = validated_data.pop("phone", "") or None
        full_name = validated_data.pop("full_name")

        # ⚠️ Qidiruv EMAIL bo'yicha: `get_or_create(phone=None)` bo'lsa, telefoni
        # yo'q istalgan foydalanuvchini (masalan Google orqali kirgan mijozni)
        # topib olardi.
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email, phone=phone, full_name=full_name, role=User.Role.BARBER
            )
        else:
            updates = []
            if user.role != User.Role.BARBER:
                user.role = User.Role.BARBER
                updates.append("role")
            if phone and not user.phone:
                user.phone = phone
                updates.append("phone")
            if full_name and not user.full_name:
                user.full_name = full_name
                updates.append("full_name")
            if updates:
                user.save(update_fields=updates)

        return Barber.objects.create(profile=user, **validated_data)

    def to_representation(self, instance):
        return AdminBarberSerializer(instance, context=self.context).data


class AdminSalonSerializer(serializers.ModelSerializer):
    barbers_count = serializers.IntegerField(read_only=True, default=0)
    cover_image = serializers.ImageField(
        required=False, allow_null=True, validators=[validate_image_upload]
    )

    class Meta:
        model = Salon
        fields = (
            "id",
            "name",
            "description",
            "specialty",
            "address",
            "district",
            "city",
            "location_lat",
            "location_lng",
            "phone",
            "cover_image",
            "owner",
            "is_active",
            "rating_avg",
            "reviews_count",
            "barbers_count",
            "created_at",
        )
        read_only_fields = ("id", "rating_avg", "reviews_count", "created_at")


class BlockActionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
