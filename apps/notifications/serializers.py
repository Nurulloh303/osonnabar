from rest_framework import serializers

from .models import Notification, PushSubscription


class PushSubscribeSerializer(serializers.Serializer):
    """Brauzerdagi `PushSubscription` obyektini shundayligicha qabul qiladi.

    Frontend `JSON.stringify(subscription)` natijasini yuborsa yetarli — u
    `{endpoint, keys: {p256dh, auth}, expirationTime}` ko'rinishida bo'ladi.
    """

    endpoint = serializers.URLField(max_length=2000)
    keys = serializers.DictField(child=serializers.CharField(), write_only=True)
    # Brauzer yuboradi, bizga kerak emas — validatsiyadan o'tishi uchun qabul qilamiz.
    expirationTime = serializers.CharField(required=False, allow_null=True, allow_blank=True)  # noqa: N815

    def validate_endpoint(self, value):
        if not value.startswith("https://"):
            raise serializers.ValidationError("Endpoint faqat https bo'lishi mumkin.")
        return value

    def validate_keys(self, value):
        missing = {"p256dh", "auth"} - set(value)
        if missing:
            raise serializers.ValidationError(f"Yetishmayotgan kalitlar: {', '.join(sorted(missing))}")
        # Faqat kerakli ikkitasini saqlaymiz — brauzer qo'shimcha maydon qo'shsa ham.
        return {"p256dh": value["p256dh"], "auth": value["auth"]}

    def create(self, validated_data):
        request = self.context["request"]
        # Endpoint bo'yicha yangilaymiz: bir brauzer qayta obuna bo'lsa nusxa
        # yaratilmaydi, boshqa foydalanuvchi kirsa obuna unga o'tadi.
        subscription, _ = PushSubscription.objects.update_or_create(
            endpoint=validated_data["endpoint"],
            defaults={
                "user": request.user,
                "auth_keys": validated_data["keys"],
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            },
        )
        return subscription


class PushSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushSubscription
        fields = ("id", "endpoint", "user_agent", "created_at", "last_success_at")
        read_only_fields = fields


class PushUnsubscribeSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2000)


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    booking_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "body",
            "kind",
            "kind_display",
            "url",
            "booking_id",
            "is_read",
            "created_at",
        )
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    """Bo'sh body — hammasini o'qilgan deb belgilaydi."""

    ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
        help_text="Bo'sh qoldirilsa — barcha o'qilmagan xabarlar belgilanadi.",
    )


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()


class VapidKeySerializer(serializers.Serializer):
    public_key = serializers.CharField()
    configured = serializers.BooleanField()
