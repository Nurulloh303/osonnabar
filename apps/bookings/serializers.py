from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.salons.models import Barber
from apps.salons.serializers import BarberShortSerializer, SalonShortSerializer

from .availability import validate_slot
from .models import Booking, BookingStatus


class ClientShortSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    avatar = serializers.ImageField(read_only=True)


class BookingSerializer(serializers.ModelSerializer):
    barber = BarberShortSerializer(read_only=True)
    salon = SalonShortSerializer(read_only=True)
    client = ClientShortSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    starts_at = serializers.DateTimeField(read_only=True)
    ends_at = serializers.DateTimeField(read_only=True)
    can_cancel = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            "id",
            "client",
            "barber",
            "salon",
            "booking_date",
            "booking_time",
            "duration_minutes",
            "starts_at",
            "ends_at",
            "service_name",
            "price",
            "status",
            "status_display",
            "client_note",
            "cancel_reason",
            "confirmed_at",
            "completed_at",
            "cancelled_at",
            "can_cancel",
            "can_review",
            "created_at",
        )

    def get_can_cancel(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_barber or request.user.is_superadmin:
            return obj.is_active
        return obj.can_be_cancelled_by_client()[0]

    def get_can_review(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated or request.user.id != obj.client_id:
            return False
        return obj.status == BookingStatus.COMPLETED and not hasattr(obj, "review")


class BookingCreateSerializer(serializers.ModelSerializer):
    """Mijoz navbat oladi.

    ⚠️ `price` va `duration_minutes` MIJOZDAN QABUL QILINMAYDI — ular ustaning
    xizmatlar ro'yxatidan server tomonda olinadi.
    """

    barber = serializers.PrimaryKeyRelatedField(queryset=Barber.objects.all())

    class Meta:
        model = Booking
        fields = ("id", "barber", "booking_date", "booking_time", "service_name", "client_note")
        read_only_fields = ("id",)
        # DRF `uniq_active_booking_slot` cheklovidan avtomatik UniqueTogetherValidator
        # yasaydi va u view'gacha ishlab, band slotga 400 + inglizcha matn qaytaradi.
        # Band slotni view o'zi `has_conflict` orqali (select_for_update ostida,
        # davomiylik kesishishini ham hisobga olib) tekshiradi va 409 `slot_taken` beradi.
        validators: list = []

    def validate_booking_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("O'tgan sanaga navbat olib bo'lmaydi.")
        max_date = today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)
        if value > max_date:
            raise serializers.ValidationError(
                f"Faqat {settings.BOOKING_MAX_DAYS_AHEAD} kun oldinga navbat olish mumkin."
            )
        return value

    def validate(self, attrs):
        barber: Barber = attrs["barber"]
        service = barber.find_service(attrs["service_name"])
        if service is None:
            available = ", ".join(str(s.get("name")) for s in (barber.services or [])) or "—"
            raise serializers.ValidationError(
                {"service_name": [f"Bu usta bunday xizmat ko'rsatmaydi. Mavjud xizmatlar: {available}"]}
            )

        attrs["price"] = int(service.get("price") or 0)
        attrs["duration_minutes"] = int(service.get("duration_minutes") or barber.default_slot_minutes)
        attrs["service_name"] = str(service["name"])
        attrs["salon"] = barber.salon

        validate_slot(barber, attrs["booking_date"], attrs["booking_time"], attrs["duration_minutes"])

        client = self.context["request"].user
        active_count = Booking.objects.filter(
            client=client, status__in=(BookingStatus.PENDING, BookingStatus.CONFIRMED)
        ).count()
        if active_count >= settings.BOOKING_MAX_ACTIVE_PER_CLIENT:
            raise serializers.ValidationError(
                f"Sizda {active_count} ta faol navbat bor. "
                f"Maksimal ruxsat: {settings.BOOKING_MAX_ACTIVE_PER_CLIENT}."
            )

        same_day = Booking.objects.filter(
            client=client,
            barber=barber,
            booking_date=attrs["booking_date"],
            status__in=(BookingStatus.PENDING, BookingStatus.CONFIRMED),
        ).exists()
        if same_day:
            raise serializers.ValidationError("Bu ustaga shu kunga allaqachon navbat olgansiz.")

        return attrs


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class BookingStatusCountSerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    confirmed = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
