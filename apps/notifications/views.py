from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Notification, PushSubscription
from .serializers import (
    MarkReadSerializer,
    NotificationSerializer,
    PushSubscribeSerializer,
    PushSubscriptionSerializer,
    PushUnsubscribeSerializer,
    UnreadCountSerializer,
    VapidKeySerializer,
)


@extend_schema(tags=["notifications"])
@extend_schema_view(
    list=extend_schema(
        summary="Xabarnomalar tarixi",
        description="Faqat joriy foydalanuvchining xabarlari. `?is_read=false` bilan filtrlash mumkin.",
    ),
    destroy=extend_schema(summary="Xabarnomani o'chirish"),
)
class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("is_read", "kind")
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)

    def get_queryset(self):
        # ⚠️ Har doim faqat o'z xabarlari — begona `id` bilan so'ralsa 404 bo'ladi.
        return Notification.objects.filter(user=self.request.user)

    # ── Qo'ng'iroqcha ────────────────────────────────────────────────────
    @extend_schema(
        responses={200: UnreadCountSerializer},
        summary="O'qilmagan xabarlar soni (qizil nuqtacha uchun)",
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": self.get_queryset().filter(is_read=False).count()})

    @extend_schema(
        request=MarkReadSerializer,
        responses={200: UnreadCountSerializer},
        summary="O'qilgan deb belgilash",
        description="Body bo'sh bo'lsa — barchasi. `{\"ids\": [...]}` bo'lsa — faqat o'shalar.",
    )
    @action(detail=False, methods=["put", "post"], url_path="read")
    def mark_read(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        queryset = self.get_queryset().filter(is_read=False)
        ids = serializer.validated_data.get("ids")
        if ids:
            queryset = queryset.filter(id__in=ids)
        queryset.update(is_read=True)

        return Response({"unread": self.get_queryset().filter(is_read=False).count()})

    # ── Push obunasi ─────────────────────────────────────────────────────
    @extend_schema(
        request=PushSubscribeSerializer,
        responses={201: PushSubscriptionSerializer},
        summary="Brauzer obunasini saqlash",
        description=(
            "Mijoz \"Ruxsat berish\" tugmasini bosgach, `pushManager.subscribe()` "
            "qaytargan obyektni shu yerga yuboring."
        ),
    )
    @action(detail=False, methods=["post"], url_path="subscribe")
    def subscribe(self, request):
        serializer = PushSubscribeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        subscription = serializer.save()
        return Response(
            PushSubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(
        request=PushUnsubscribeSerializer,
        responses={204: None},
        summary="Obunani bekor qilish",
    )
    @action(detail=False, methods=["post"], url_path="unsubscribe")
    def unsubscribe(self, request):
        serializer = PushUnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushSubscription.objects.filter(
            user=request.user, endpoint=serializer.validated_data["endpoint"]
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        responses={200: PushSubscriptionSerializer(many=True)},
        summary="Mening ulangan qurilmalarim",
    )
    @action(detail=False, methods=["get"], url_path="subscriptions")
    def subscriptions(self, request):
        rows = PushSubscription.objects.filter(user=request.user)
        return Response(PushSubscriptionSerializer(rows, many=True).data)

    @extend_schema(
        responses={200: VapidKeySerializer},
        summary="VAPID public key",
        description=(
            "Frontend `pushManager.subscribe({applicationServerKey})` uchun ishlatadi. "
            "Public key maxfiy emas — u brauzerga baribir ochiq ko'rinadi."
        ),
        auth=[],
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="vapid-key",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def vapid_key(self, request):
        return Response(
            {
                "public_key": settings.VAPID_PUBLIC_KEY,
                "configured": bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY),
            }
        )
