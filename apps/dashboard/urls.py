from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "dashboard"

admin_router = DefaultRouter()
admin_router.register("users", views.AdminUserViewSet, basename="admin-user")
admin_router.register("barbers", views.AdminBarberViewSet, basename="admin-barber")
admin_router.register("salons", views.AdminSalonViewSet, basename="admin-salon")

urlpatterns = [
    path("barber/me/stats/", views.BarberStatsView.as_view(), name="barber-stats"),
    path("super-admin/stats/", views.SuperAdminStatsView.as_view(), name="admin-stats"),
    path("super-admin/", include(admin_router.urls)),
]
