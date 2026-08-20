from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import BookingStatus
from apps.common.permissions import IsBarber, IsSuperAdmin
from apps.salons.models import Barber, Salon

from .serializers import (
    AdminBarberCreateSerializer,
    AdminBarberSerializer,
    AdminSalonSerializer,
    AdminUserSerializer,
    BlockActionSerializer,
)
from .stats import barber_dashboard, superadmin_dashboard

User = get_user_model()

PERIOD_PARAM = OpenApiParameter(
    "period", str, description="`day` | `week` | `month` (default) | `year` | `all`"
)


# ── Usta paneli ───────────────────────────────────────────────────────────
@extend_schema(tags=["barber-panel"])
class BarberStatsView(APIView):
    """Usta uchun daromad va navbatlar statistikasi."""

    permission_classes = [IsAuthenticated, IsBarber]

    @extend_schema(
        parameters=[PERIOD_PARAM],
        responses={200: OpenApiTypes.OBJECT},
        summary="Usta statistikasi",
    )
    def get(self, request):
        barber = Barber.objects.filter(profile=request.user).first()
        if barber is None:
            raise NotFound("Usta profili topilmadi.")
        period = request.query_params.get("period", "month")
        return Response(barber_dashboard(barber, period))


# ── Super admin ───────────────────────────────────────────────────────────
@extend_schema(tags=["admin-panel"])
class SuperAdminStatsView(APIView):
    """Butun platforma bo'yicha umumiy ko'rsatkichlar (`/super-admin` sahifasi uchun)."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        parameters=[PERIOD_PARAM], responses={200: OpenApiTypes.OBJECT}, summary="Platforma statistikasi"
    )
    def get(self, request):
        return Response(superadmin_dashboard(request.query_params.get("period", "month")))


@extend_schema(tags=["admin-panel"])
@extend_schema_view(
    list=extend_schema(summary="Foydalanuvchilar ro'yxati"),
    retrieve=extend_schema(summary="Foydalanuvchi kartochkasi"),
)
class AdminUserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filterset_fields = ("role", "is_active", "is_phone_verified")
    search_fields = ("full_name", "phone", "email")
    ordering_fields = ("created_at", "full_name", "last_login")
    ordering = ("-created_at",)

    def get_queryset(self):
        return User.objects.select_related("barber").annotate(
            bookings_count=Count("bookings", distinct=True),
            total_spent=Sum("bookings__price", filter=Q(bookings__status=BookingStatus.COMPLETED), default=0),
        )

    @extend_schema(request=BlockActionSerializer, responses={200: AdminUserSerializer}, summary="Bloklash")
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        user = self.get_object()
        if user.is_superadmin:
            raise ValidationError("Super adminni bloklab bo'lmaydi.")
        user.is_active = False
        user.save(update_fields=["is_active"])
        # Usta bo'lsa — profili ham bloklanadi, yangi navbat tushmaydi
        Barber.objects.filter(profile=user).update(status=Barber.Status.BLOCKED)
        return Response(self.get_serializer(self.get_queryset().get(pk=user.pk)).data)

    @extend_schema(request=None, responses={200: AdminUserSerializer}, summary="Blokdan chiqarish")
    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        Barber.objects.filter(profile=user).update(status=Barber.Status.ACTIVE)
        return Response(self.get_serializer(self.get_queryset().get(pk=user.pk)).data)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: AdminUserSerializer},
        summary="Rolni o'zgartirish",
        description="Body: `{\"role\": \"client|barber|superadmin\"}`",
    )
    @action(detail=True, methods=["post"], url_path="set-role")
    def set_role(self, request, pk=None):
        user = self.get_object()
        role = request.data.get("role")
        if role not in User.Role.values:
            raise ValidationError({"role": [f"Ruxsat etilgan qiymatlar: {', '.join(User.Role.values)}"]})
        user.role = role
        user.is_staff = role == User.Role.SUPERADMIN
        user.save(update_fields=["role", "is_staff"])
        return Response(self.get_serializer(self.get_queryset().get(pk=user.pk)).data)


@extend_schema(tags=["admin-panel"])
@extend_schema_view(
    list=extend_schema(summary="Ustalar ro'yxati (admin)"),
    create=extend_schema(summary="Yangi usta qo'shish"),
)
class AdminBarberViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filterset_fields = ("status", "specialty", "salon")
    search_fields = ("profile__full_name", "profile__phone", "salon__name")
    ordering_fields = ("created_at", "rating_avg", "completed_bookings")
    ordering = ("-created_at",)

    def get_serializer_class(self):
        return AdminBarberCreateSerializer if self.action == "create" else AdminBarberSerializer

    def get_queryset(self):
        return (
            Barber.objects.select_related("profile", "salon")
            .annotate(
                revenue_total=Sum(
                    "bookings__price", filter=Q(bookings__status=BookingStatus.COMPLETED), default=0
                ),
                bookings_total=Count("bookings", distinct=True),
            )
            .order_by("-created_at")
        )

    @extend_schema(request=BlockActionSerializer, responses={200: AdminBarberSerializer}, summary="Bloklash")
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        barber = self.get_object()
        barber.status = Barber.Status.BLOCKED
        barber.save(update_fields=["status"])
        return Response(AdminBarberSerializer(barber, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses={200: AdminBarberSerializer}, summary="Faollashtirish")
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        barber = self.get_object()
        barber.status = Barber.Status.ACTIVE
        barber.save(update_fields=["status"])
        return Response(AdminBarberSerializer(barber, context=self.get_serializer_context()).data)


@extend_schema(tags=["admin-panel"])
@extend_schema_view(list=extend_schema(summary="Salonlar (admin CRUD)"))
class AdminSalonViewSet(viewsets.ModelViewSet):
    serializer_class = AdminSalonSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filterset_fields = ("is_active", "specialty", "city", "district")
    search_fields = ("name", "address", "district")
    ordering = ("-created_at",)

    def get_queryset(self):
        return Salon.objects.annotate(barbers_count=Count("barbers")).order_by("-created_at")
