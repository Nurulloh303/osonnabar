from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import ReadOnlyOrAuthenticated

from .models import Review
from .serializers import BarberReplySerializer, ReviewSerializer


@extend_schema(tags=["reviews"])
@extend_schema_view(
    list=extend_schema(
        summary="Sharhlar ro'yxati",
        parameters=[
            OpenApiParameter("barber", OpenApiTypes.UUID, description="Usta bo'yicha filtr"),
            OpenApiParameter("salon", OpenApiTypes.UUID, description="Salon bo'yicha filtr"),
            OpenApiParameter("rating", OpenApiTypes.INT, description="Aniq baho (1–5)"),
        ],
    ),
    create=extend_schema(summary="Sharh qoldirish (yakunlangan navbat uchun)"),
)
class ReviewViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ReviewSerializer
    permission_classes = [ReadOnlyOrAuthenticated]
    filterset_fields = ("barber", "salon", "rating")
    ordering_fields = ("created_at", "rating")
    ordering = ("-created_at",)

    def get_queryset(self):
        return Review.objects.select_related("client", "booking", "barber__profile")

    def perform_destroy(self, instance):
        user = self.request.user
        if not (user.is_superadmin or instance.client_id == user.id):
            raise PermissionDenied("Bu sharhni o'chira olmaysiz.")
        instance.delete()

    @extend_schema(
        request=BarberReplySerializer,
        responses={200: ReviewSerializer},
        summary="Sharhga javob berish (usta)",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def reply(self, request, pk=None):
        review = self.get_object()
        if not (request.user.is_superadmin or review.barber.profile_id == request.user.id):
            raise PermissionDenied("Bu sharh sizga tegishli emas.")

        serializer = BarberReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review.barber_reply = serializer.validated_data["barber_reply"]
        review.save(update_fields=["barber_reply", "updated_at"])
        return Response(ReviewSerializer(review, context=self.get_serializer_context()).data)

    @extend_schema(
        summary="Reyting taqsimoti (1★…5★)",
        parameters=[OpenApiParameter("barber", OpenApiTypes.UUID, required=True)],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="summary")
    def rating_summary(self, request):
        qs = self.filter_queryset(self.get_queryset())
        rows = qs.values("rating").annotate(count=Count("id"))
        distribution = {str(i): 0 for i in range(1, 6)}
        total, weighted = 0, 0
        for row in rows:
            distribution[str(row["rating"])] = row["count"]
            total += row["count"]
            weighted += row["rating"] * row["count"]
        return Response(
            {
                "total": total,
                "average": round(weighted / total, 2) if total else 0,
                "distribution": distribution,
            }
        )
