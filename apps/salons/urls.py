from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "salons"

router = DefaultRouter()
router.register("salons", views.SalonViewSet, basename="salon")
router.register("barbers", views.BarberViewSet, basename="barber")

barber_panel = DefaultRouter()
barber_panel.register("schedule", views.BarberScheduleViewSet, basename="barber-schedule")
barber_panel.register("days-off", views.BarberDayOffViewSet, basename="barber-dayoff")

urlpatterns = [
    path("", include(router.urls)),
    path("barber/me/", views.BarberMeView.as_view(), name="barber-me"),
    path("barber/me/", include(barber_panel.urls)),
]
