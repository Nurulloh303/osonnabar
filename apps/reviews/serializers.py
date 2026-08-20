from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus

from .models import Review


class ReviewAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.SerializerMethodField()
    avatar = serializers.ImageField(read_only=True)

    def get_full_name(self, obj) -> str:
        """Maxfiylik: to'liq ism o'rniga "Nurulloh A." ko'rinishi."""
        parts = (obj.full_name or "").split()
        if not parts:
            return "Mijoz"
        if len(parts) == 1:
            return parts[0]
        return f"{parts[0]} {parts[1][0]}."


class ReviewSerializer(serializers.ModelSerializer):
    client = ReviewAuthorSerializer(read_only=True)
    service_name = serializers.CharField(source="booking.service_name", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "booking",
            "barber",
            "salon",
            "client",
            "service_name",
            "rating",
            "comment",
            "barber_reply",
            "created_at",
        )
        read_only_fields = ("id", "barber", "salon", "client", "barber_reply", "created_at")

    def validate_booking(self, booking: Booking):
        request = self.context["request"]
        if booking.client_id != request.user.id:
            raise serializers.ValidationError("Bu navbat sizga tegishli emas.")
        if booking.status != BookingStatus.COMPLETED:
            raise serializers.ValidationError("Sharh faqat yakunlangan xizmat uchun yoziladi.")
        if Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError("Bu navbat uchun sharh allaqachon yozilgan.")
        return booking

    def create(self, validated_data):
        booking: Booking = validated_data["booking"]
        return Review.objects.create(
            client=booking.client,
            barber=booking.barber,
            salon=booking.salon,
            **validated_data,
        )


class BarberReplySerializer(serializers.Serializer):
    barber_reply = serializers.CharField(max_length=1000)
