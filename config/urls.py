import re

from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache
from django.views.static import serve as serve_static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


@never_cache
def healthcheck(_request):
    """Load balancer / Docker healthcheck uchun. Bazani ham tekshiradi."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:  # noqa: BLE001 — sabab muhim emas, holat muhim
        db_ok = False

    payload = {"status": "ok" if db_ok else "degraded", "service": "osonnavbat-api", "database": db_ok}
    return JsonResponse(payload, status=200 if db_ok else 503)


api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.salons.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.reviews.urls")),
    path("", include("apps.dashboard.urls")),
]

urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    path("health/", healthcheck),
    path("api/v1/", include((api_v1, "v1"))),
]

if settings.ENABLE_API_DOCS:
    # Kim ko'ra olishi `SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]` bilan boshqariladi:
    # DEBUG'da hamma, prodda faqat staff.
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]

if settings.SERVE_MEDIA and settings.STORAGE_BACKEND == "local":
    # ⚠️ Ilgari bu `static()` helper'i bilan yozilgandi, u esa DEBUG=False bo'lsa
    # bo'sh ro'yxat qaytaradi — natijada prodda barcha avatar va muqova rasmlari
    # 404 bo'lardi. Shuning uchun route'ni to'g'ridan-to'g'ri qo'yamiz.
    # Nginx `/media/` ni o'zi bera olsa — `SERVE_MEDIA=False` qiling, tezroq bo'ladi.
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve_static,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
