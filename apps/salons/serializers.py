from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.common.uploads import validate_image_upload

from .models import Barber, BarberDayOff, BarberSchedule, Salon, Weekday


class ServiceItemSerializer(serializers.Serializer):
    """`Barber.services` JSON ro'yxatining bitta elementi."""

    name = serializers.CharField(max_length=100)
    price = serializers.IntegerField(min_value=0, help_text="so'mda, butun son")
    duration_minutes = serializers.IntegerField(min_value=10, max_value=240, required=False, default=30)


class SalonShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salon
        fields = ("id", "name", "address", "district", "city", "location_lat", "location_lng")


class SalonListSerializer(serializers.ModelSerializer):
    barbers_count = serializers.IntegerField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()

    class Meta:
        model = Salon
        fields = (
            "id",
            "name",
            "specialty",
            "address",
            "district",
            "city",
            "location_lat",
            "location_lng",
            "phone",
            "cover_image",
            "rating_avg",
            "reviews_count",
            "barbers_count",
            "price_from",
            "distance_km",
            "is_active",
        )

    def get_distance_km(self, obj) -> float | None:
        value = getattr(obj, "distance_km", None)
        return round(value, 2) if value is not None else None

    def get_price_from(self, obj) -> int | None:
        prices = [
            s["price"]
            for barber in obj.barbers.all()
            for s in (barber.services or [])
            if isinstance(s, dict) and isinstance(s.get("price"), int)
        ]
        return min(prices) if prices else None


class BarberShortSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="profile.full_name", read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Barber
        fields = ("id", "full_name", "avatar", "specialty", "rating_avg", "reviews_count", "status")

    def get_avatar(self, obj) -> str | None:
        request = self.context.get("request")
        image = obj.avatar or obj.profile.avatar
        if not image:
            return None
        return request.build_absolute_uri(image.url) if request else image.url


class BarberListSerializer(BarberShortSerializer):
    salon = SalonShortSerializer(read_only=True)
    services = ServiceItemSerializer(many=True, read_only=True)
    distance_km = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    location_lat = serializers.FloatField(source="lat", read_only=True)
    location_lng = serializers.FloatField(source="lng", read_only=True)

    class Meta(BarberShortSerializer.Meta):
        fields = BarberShortSerializer.Meta.fields + (
            "salon",
            "bio",
            "experience_years",
            "services",
            "price_from",
            "location_lat",
            "location_lng",
            "distance_km",
            "completed_bookings",
        )

    def get_distance_km(self, obj) -> float | None:
        value = getattr(obj, "distance_km", None)
        return round(value, 2) if value is not None else None

    def get_price_from(self, obj) -> int | None:
        prices = [s["price"] for s in (obj.services or []) if isinstance(s, dict) and isinstance(s.get("price"), int)]
        return min(prices) if prices else None


class BarberScheduleSerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = BarberSchedule
        fields = (
            "id",
            "weekday",
            "weekday_display",
            "is_working",
            "start_time",
            "end_time",
            "break_start",
            "break_end",
            "slot_minutes",
        )

    def validate(self, attrs):
        start = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        if start and end and end <= start:
            raise serializers.ValidationError({"end_time": ["Tugash vaqti boshlanishdan keyin bo'lishi kerak."]})

        b_start = attrs.get("break_start") or getattr(self.instance, "break_start", None)
        b_end = attrs.get("break_end") or getattr(self.instance, "break_end", None)
        if bool(b_start) != bool(b_end):
            raise serializers.ValidationError({"break_start": ["Tanaffus boshi va oxiri birga ko'rsatilishi kerak."]})
        if b_start and b_end and b_end <= b_start:
            raise serializers.ValidationError({"break_end": ["Tanaffus oxiri boshidan keyin bo'lishi kerak."]})
        return attrs


class BarberDayOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = BarberDayOff
        fields = ("id", "date", "reason")


class BarberDetailSerializer(BarberListSerializer):
    schedules = BarberScheduleSerializer(many=True, read_only=True)
    days_off = serializers.SerializerMethodField()

    class Meta(BarberListSerializer.Meta):
        fields = BarberListSerializer.Meta.fields + ("schedules", "days_off", "default_slot_minutes", "created_at")

    def get_days_off(self, obj) -> list[str]:
        from django.utils import timezone

        return [
            d.date.isoformat()
            for d in obj.days_off.filter(date__gte=timezone.localdate()).order_by("date")[:60]
        ]


class SalonDetailSerializer(SalonListSerializer):
    barbers = BarberShortSerializer(many=True, read_only=True)

    class Meta(SalonListSerializer.Meta):
        fields = SalonListSerializer.Meta.fields + ("description", "barbers", "created_at")


class BarberSelfSerializer(serializers.ModelSerializer):
    """Usta o'z profilini tahrirlaydi (`/barber/me/`)."""

    profile = UserSerializer(read_only=True)
    services = ServiceItemSerializer(many=True, required=False)
    avatar = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_upload])

    class Meta:
        model = Barber
        fields = (
            "id",
            "profile",
            "salon",
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
        )
        read_only_fields = ("id", "status", "rating_avg", "reviews_count", "completed_bookings")

    def validate_services(self, value):
        names = [s["name"].strip().casefold() for s in value]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Xizmat nomlari takrorlanmasligi kerak.")
        return value


class AvailableSlotSerializer(serializers.Serializer):
    time = serializers.CharField(help_text="HH:MM")
    is_available = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_null=True)


class AvailableSlotsResponseSerializer(serializers.Serializer):
    barber_id = serializers.UUIDField()
    date = serializers.DateField()
    weekday = serializers.ChoiceField(choices=Weekday.choices)
    is_working_day = serializers.BooleanField()
    slot_minutes = serializers.IntegerField()
    slots = AvailableSlotSerializer(many=True)
