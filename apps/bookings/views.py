import logging

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import BusinessRuleError, SlotTakenError
from apps.salons.models import Barber

from .availability import has_conflict
from .filters import BookingFilter
from .models import Booking, BookingStatus
from .serializers import (
    BookingCancelSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    BookingStatusCountSerializer,
)

logger = logging.getLogger("apps.bookings")


@extend_schema(tags=["bookings"])
@extend_schema_view(
    list=extend_schema(
        summary="Navbatlar ro'yxati",
        description=(
            "Mijoz — o'z bronlarini, usta — o'ziga tushgan bronlarni, super admin — hammasini ko'radi.\n\n"
            "Filtrlar: `?status=pending&status=confirmed`, `?scope=upcoming|past|today`, "
            "`?date_from=&date_to=`."
        ),
        parameters=[OpenApiParameter("scope", str, description="upcoming | past | today")],
    ),
    retrieve=extend_schema(summary="Bitta navbat"),
    create=extend_schema(summary="Navbatga yozilish"),
)
class BookingViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    filterset_class = BookingFilter
    ordering_fields = ("booking_date", "booking_time", "created_at", "price")
    ordering = ("-booking_date", "-booking_time")
    search_fields = ("service_name", "barber__profile__full_name", "client__full_name", "client__phone")

    def get_serializer_class(self):
        return BookingCreateSerializer if self.action == "create" else BookingSerializer

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "booking_create"
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related(
            "barber", "barber__profile", "barber__salon", "salon", "client"
        ).prefetch_related("review")

        if user.is_superadmin:
            return qs
        if user.is_barber:
            return qs.filter(barber__profile=user)
        return qs.filter(client=user)

    # ── yaratish ──────────────────────────────────────────────────────
    def create(self, request, *args, **kwargs):
        if not request.user.is_client:
            raise PermissionDenied("Navbatga faqat mijozlar yozila oladi.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        barber = data["barber"]

        try:
            with transaction.atomic():
                # Ustaning qatorini bloklaymiz — bir vaqtda kelgan so'rovlar navbatga tizilib qoladi
                Barber.objects.select_for_update().get(pk=barber.pk)

                if has_conflict(
                    barber.pk, data["booking_date"], data["booking_time"], data["duration_minutes"]
                ):
                    raise SlotTakenError()

                booking = Booking.objects.create(client=request.user, **data)
        except IntegrityError as exc:
            # Ikkinchi himoya qatlami: DB dagi qisman unikal indeks
            if "uniq_active_booking_slot" in str(exc):
                raise SlotTakenError() from exc
            raise

        logger.info("Yangi bron %s: %s → %s", booking.id, request.user.phone, barber.pk)
        output = BookingSerializer(booking, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

    # ── holat o'zgartirish ────────────────────────────────────────────
    def _get_barber_owned(self, request) -> Booking:
        booking = self.get_object()
        if not (request.user.is_superadmin or booking.barber.profile_id == request.user.id):
            raise PermissionDenied("Bu navbat sizga tegishli emas.")
        return booking

    @extend_schema(request=None, responses={200: BookingSerializer}, summary="Tasdiqlash (usta)")
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        booking = self._get_barber_owned(request)
        if booking.status != BookingStatus.PENDING:
            raise BusinessRuleError("Faqat 'kutilmoqda' holatidagi navbatni tasdiqlash mumkin.")

        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = timezone.now()
        booking.save(update_fields=["status", "confirmed_at", "updated_at"])
        return Response(BookingSerializer(booking, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses={200: BookingSerializer}, summary="Yakunlash (usta)")
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        booking = self._get_barber_owned(request)
        if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
            raise BusinessRuleError("Bu navbatni yakunlab bo'lmaydi.")

        with transaction.atomic():
            booking.status = BookingStatus.COMPLETED
            booking.completed_at = timezone.now()
            booking.save(update_fields=["status", "completed_at", "updated_at"])
            # Denormalizatsiyalangan hisoblagichni yangilaymiz (ro'yxatlarni tez saralash uchun)
            completed = Booking.objects.filter(
                barber_id=booking.barber_id, status=BookingStatus.COMPLETED
            ).count()
            Barber.objects.filter(pk=booking.barber_id).update(completed_bookings=completed)

        return Response(BookingSerializer(booking, context=self.get_serializer_context()).data)

    @extend_schema(
        request=BookingCancelSerializer, responses={200: BookingSerializer}, summary="Bekor qilish"
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        user = request.user
        is_owner_client = booking.client_id == user.id
        is_owner_barber = booking.barber.profile_id == user.id

        if not (is_owner_client or is_owner_barber or user.is_superadmin):
            raise PermissionDenied("Bu navbat sizga tegishli emas.")

        if is_owner_client and not (is_owner_barber or user.is_superadmin):
            allowed, message = booking.can_be_cancelled_by_client()
            if not allowed:
                raise BusinessRuleError(message)
        elif not booking.is_active:
            raise BusinessRuleError("Bu navbat allaqachon yopilgan.")

        serializer = BookingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancelled_by = user
        booking.cancel_reason = serializer.validated_data.get("reason", "")
        booking.save(
            update_fields=["status", "cancelled_at", "cancelled_by", "cancel_reason", "updated_at"]
        )
        return Response(BookingSerializer(booking, context=self.get_serializer_context()).data)

    @extend_schema(responses={200: BookingStatusCountSerializer}, summary="Holatlar bo'yicha sanoq")
    @action(detail=False, methods=["get"], url_path="counts")
    def counts(self, request):
        agg = self.filter_queryset(self.get_queryset()).aggregate(
            pending=Count("id", filter=Q(status=BookingStatus.PENDING)),
            confirmed=Count("id", filter=Q(status=BookingStatus.CONFIRMED)),
            completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status=BookingStatus.CANCELLED)),
        )
        return Response(agg)
