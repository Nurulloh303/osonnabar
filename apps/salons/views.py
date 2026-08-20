from datetime import timedelta

from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.geo import bounding_box, distance_expression
from apps.common.permissions import IsBarber

from .filters import BarberFilter, SalonFilter
from .models import Barber, BarberDayOff, BarberSchedule, Salon, Weekday
from .serializers import (
    AvailableSlotsResponseSerializer,
    BarberDayOffSerializer,
    BarberDetailSerializer,
    BarberListSerializer,
    BarberScheduleSerializer,
    BarberSelfSerializer,
    SalonDetailSerializer,
    SalonListSerializer,
)

GEO_PARAMS = [
    OpenApiParameter("lat", OpenApiTypes.FLOAT, description="Foydalanuvchi kengligi (Yandex Maps)"),
    OpenApiParameter("lng", OpenApiTypes.FLOAT, description="Foydalanuvchi uzunligi"),
    OpenApiParameter("radius", OpenApiTypes.FLOAT, description="Qidiruv radiusi, km (default: cheklovsiz)"),
    OpenApiParameter(
        "ordering",
        OpenApiTypes.STR,
        description="`distance`, `-rating_avg`, `rating_avg`, `-reviews_count`, `name`",
    ),
]


class GeoQuerysetMixin:
    """`?lat=&lng=&radius=` bo'yicha masofa hisoblash va saralash."""

    lat_field = "location_lat"
    lng_field = "location_lng"

    def _geo_params(self):
        params = self.request.query_params
        lat, lng = params.get("lat"), params.get("lng")
        if lat in (None, "") or lng in (None, ""):
            return None
        try:
            radius = float(params["radius"]) if params.get("radius") else None
            return float(lat), float(lng), radius
        except (TypeError, ValueError):
            raise ValidationError({"lat": ["`lat`, `lng`, `radius` son bo'lishi kerak."]})

    def apply_geo(self, queryset):
        geo = self._geo_params()
        if geo is None:
            return queryset, False

        lat, lng, radius = geo
        if radius:
            min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius)
            queryset = queryset.filter(
                **{
                    f"{self.lat_field}__range": (min_lat, max_lat),
                    f"{self.lng_field}__range": (min_lng, max_lng),
                }
            )
        queryset = queryset.annotate(
            distance_km=distance_expression(lat, lng, self.lat_field, self.lng_field)
        )
        if radius:
            queryset = queryset.filter(distance_km__lte=radius)
        return queryset, True


@extend_schema(tags=["salons"])
@extend_schema_view(
    list=extend_schema(summary="Salonlar ro'yxati / xarita", parameters=GEO_PARAMS),
    retrieve=extend_schema(summary="Salon tafsilotlari"),
)
class SalonViewSet(GeoQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    filterset_class = SalonFilter
    search_fields = ("name", "address", "district", "description")
    ordering_fields = ("rating_avg", "reviews_count", "name", "created_at")
    ordering = ("-rating_avg",)

    def get_serializer_class(self):
        return SalonDetailSerializer if self.action == "retrieve" else SalonListSerializer

    def get_queryset(self):
        qs = (
            Salon.objects.filter(is_active=True)
            .annotate(barbers_count=Count("barbers", filter=Q(barbers__status=Barber.Status.ACTIVE)))
            .prefetch_related(
                Prefetch(
                    "barbers",
                    queryset=Barber.objects.filter(status=Barber.Status.ACTIVE).select_related("profile"),
                )
            )
        )
        qs, has_geo = self.apply_geo(qs)
        if has_geo and self.request.query_params.get("ordering") in (None, "", "distance"):
            qs = qs.order_by("distance_km")
        return qs


@extend_schema(tags=["barbers"])
@extend_schema_view(
    list=extend_schema(summary="Ustalar ro'yxati / xarita", parameters=GEO_PARAMS),
    retrieve=extend_schema(summary="Usta tafsilotlari (jadval bilan)"),
)
class BarberViewSet(GeoQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    # Ustaning o'z koordinatasi bo'lmasa — salonnikiga tushamiz (pastdagi annotate)
    lat_field = "eff_lat"
    lng_field = "eff_lng"
    filterset_class = BarberFilter
    search_fields = ("profile__full_name", "bio", "salon__name", "salon__district")
    ordering_fields = ("rating_avg", "reviews_count", "completed_bookings", "experience_years", "created_at")
    ordering = ("-rating_avg",)

    def get_serializer_class(self):
        return BarberDetailSerializer if self.action == "retrieve" else BarberListSerializer

    def get_queryset(self):
        qs = (
            Barber.objects.filter(status=Barber.Status.ACTIVE, profile__is_active=True)
            .select_related("profile", "salon")
            .prefetch_related("schedules", "days_off")
            .annotate(
                eff_lat=Coalesce("location_lat", "salon__location_lat"),
                eff_lng=Coalesce("location_lng", "salon__location_lng"),
            )
        )
        qs, has_geo = self.apply_geo(qs)
        if has_geo and self.request.query_params.get("ordering") in (None, "", "distance"):
            qs = qs.order_by("distance_km")
        return qs

    @extend_schema(
        summary="Ustaning bo'sh vaqtlari",
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE, required=True, description="YYYY-MM-DD"),
            OpenApiParameter("service", OpenApiTypes.STR, description="Xizmat nomi (davomiylikni hisobga olish uchun)"),
        ],
        responses={200: AvailableSlotsResponseSerializer},
    )
    @action(detail=True, methods=["get"], url_path="available-slots", permission_classes=[AllowAny])
    def available_slots(self, request, pk=None):
        from apps.bookings.availability import get_day_availability

        barber = self.get_object()
        raw_date = request.query_params.get("date")
        if not raw_date:
            raise ValidationError({"date": ["`date` parametri majburiy (YYYY-MM-DD)."]})

        from django.utils.dateparse import parse_date

        on_date = parse_date(raw_date)
        if on_date is None:
            raise ValidationError({"date": ["Sana formati noto'g'ri. Namuna: 2026-08-15"]})

        today = timezone.localdate()
        from django.conf import settings

        if on_date < today:
            raise ValidationError({"date": ["O'tgan sana uchun navbat ochilmaydi."]})
        if on_date > today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD):
            raise ValidationError(
                {"date": [f"Faqat {settings.BOOKING_MAX_DAYS_AHEAD} kun oldinga navbat olish mumkin."]}
            )

        duration = None
        service_name = request.query_params.get("service")
        if service_name:
            service = barber.find_service(service_name)
            if service is None:
                raise ValidationError({"service": ["Bu usta bunday xizmat ko'rsatmaydi."]})
            duration = int(service.get("duration_minutes") or barber.default_slot_minutes)

        data = get_day_availability(barber, on_date, duration)
        return Response(data)

    @extend_schema(summary="Ustaning eng yaqin bo'sh vaqti", responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="next-slot", permission_classes=[AllowAny])
    def next_slot(self, request, pk=None):
        from apps.bookings.availability import next_available_slot

        slot = next_available_slot(self.get_object())
        return Response({"next_slot": slot})


# ── Usta paneli ───────────────────────────────────────────────────────────
@extend_schema(tags=["barber-panel"], summary="Usta o'z profili")
class BarberMeView(RetrieveUpdateAPIView):
    serializer_class = BarberSelfSerializer
    permission_classes = [IsAuthenticated, IsBarber]
    http_method_names = ["get", "patch", "put", "head", "options"]

    def get_object(self):
        barber = Barber.objects.filter(profile=self.request.user).select_related("profile", "salon").first()
        if barber is None:
            raise NotFound("Sizga biriktirilgan usta profili topilmadi. Administratorga murojaat qiling.")
        return barber


@extend_schema(tags=["barber-panel"])
class BarberScheduleViewSet(viewsets.ModelViewSet):
    """Usta o'z ish jadvalini boshqaradi (`/barber/me/schedule/`)."""

    serializer_class = BarberScheduleSerializer
    permission_classes = [IsAuthenticated, IsBarber]
    pagination_class = None

    def _barber(self) -> Barber:
        barber = Barber.objects.filter(profile=self.request.user).first()
        if barber is None:
            raise NotFound("Usta profili topilmadi.")
        return barber

    def get_queryset(self):
        return BarberSchedule.objects.filter(barber=self._barber()).order_by("weekday")

    def perform_create(self, serializer):
        serializer.save(barber=self._barber())

    @extend_schema(
        summary="Haftalik jadvalni bir zarbda saqlash",
        request=BarberScheduleSerializer(many=True),
        responses={200: BarberScheduleSerializer(many=True)},
    )
    @action(detail=False, methods=["put"], url_path="bulk")
    def bulk(self, request):
        serializer = BarberScheduleSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        barber = self._barber()

        weekdays = [item["weekday"] for item in serializer.validated_data]
        if len(weekdays) != len(set(weekdays)):
            raise ValidationError("Har bir hafta kuni faqat bir marta kelishi kerak.")

        for item in serializer.validated_data:
            BarberSchedule.objects.update_or_create(
                barber=barber, weekday=item["weekday"], defaults={k: v for k, v in item.items() if k != "weekday"}
            )
        rows = BarberSchedule.objects.filter(barber=barber).order_by("weekday")
        return Response(BarberScheduleSerializer(rows, many=True).data)

    @extend_schema(summary="Hafta kunlari lug'ati", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="weekdays", permission_classes=[AllowAny])
    def weekdays(self, request):
        return Response([{"value": v, "label": label} for v, label in Weekday.choices])


@extend_schema(tags=["barber-panel"])
class BarberDayOffViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Dam olish kunlari (`/barber/me/days-off/`)."""

    serializer_class = BarberDayOffSerializer
    permission_classes = [IsAuthenticated, IsBarber]
    pagination_class = None

    def _barber(self) -> Barber:
        barber = Barber.objects.filter(profile=self.request.user).first()
        if barber is None:
            raise NotFound("Usta profili topilmadi.")
        return barber

    def get_queryset(self):
        return BarberDayOff.objects.filter(barber=self._barber()).order_by("date")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        barber = self._barber()

        from apps.bookings.models import Booking, BookingStatus

        clash = Booking.objects.filter(
            barber=barber,
            booking_date=serializer.validated_data["date"],
            status__in=(BookingStatus.PENDING, BookingStatus.CONFIRMED),
        ).count()
        if clash:
            raise ValidationError(
                {"date": [f"Bu kunda {clash} ta faol navbat bor. Avval ularni bekor qiling."]}
            )

        obj, created = BarberDayOff.objects.get_or_create(
            barber=barber,
            date=serializer.validated_data["date"],
            defaults={"reason": serializer.validated_data.get("reason", "")},
        )
        return Response(
            BarberDayOffSerializer(obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
