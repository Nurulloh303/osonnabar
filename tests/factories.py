"""Testlar uchun yordamchi obyektlar."""

import importlib
from datetime import time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.cookies import issue_tokens
from apps.salons.models import Barber, BarberSchedule, Salon

User = get_user_model()


def reload_urlconf() -> None:
    """URL jadvalini qaytadan quradi.

    `apps/accounts/urls.py` `AUTH_SMS_ENABLED` ga qarab OTP manzillarini
    ro'yxatga oladi. Bu shart modul import qilinganda BIR MARTA bajariladi,
    shuning uchun `override_settings` bilan bayroqni o'zgartirish yetarli emas —
    modullarni qayta yuklash kerak.
    """
    for name in ("apps.accounts.urls", "config.urls"):
        importlib.reload(importlib.import_module(name))
    clear_url_caches()


@receiver(setting_changed)
def _reload_urls_when_flag_changes(sender, setting, **kwargs):
    """`AUTH_SMS_ENABLED` o'zgarganda URL jadvalini avtomatik qayta quradi.

    `tearDownClass` da qo'lda qilib bo'lmaydi: Django `override_settings` ni
    `addClassCleanup` orqali o'chiradi, ya'ni `tearDownClass` tugagandan KEYIN.
    Signal esa sozlama qo'llangandan/qaytarilgandan keyin darhol keladi —
    ikkala yo'nalishda ham to'g'ri ishlaydi.
    """
    if setting == "AUTH_SMS_ENABLED":
        reload_urlconf()

DEFAULT_SERVICES = [
    {"name": "Soch olish", "price": 50000, "duration_minutes": 30},
    {"name": "Soqol olish", "price": 30000, "duration_minutes": 60},
]


def make_client_user(phone="+998907000001", name="Test Mijoz") -> User:
    return User.objects.create_user(phone=phone, full_name=name, is_phone_verified=True)


def make_barber(phone="+998901000001", name="Test Usta", *, salon=None, services=None) -> Barber:
    profile = User.objects.create_user(
        phone=phone, full_name=name, role=User.Role.BARBER, is_phone_verified=True
    )
    salon = salon or Salon.objects.create(
        name="Test Salon", address="Toshkent", location_lat=41.3111, location_lng=69.2797
    )
    barber = Barber.objects.create(
        profile=profile,
        salon=salon,
        services=services if services is not None else DEFAULT_SERVICES,
    )
    for weekday in range(7):
        BarberSchedule.objects.create(
            barber=barber,
            weekday=weekday,
            is_working=True,
            start_time=time(9, 0),
            end_time=time(20, 0),
            slot_minutes=30,
        )
    return barber


def make_superadmin(phone="+998901111111") -> User:
    return User.objects.create_superuser(phone=phone, full_name="Admin", password="admin12345")


def auth_client(user) -> APIClient:
    """httpOnly cookie orqali autentifikatsiya qilingan klient."""
    access, refresh = issue_tokens(user)
    api = APIClient()
    api.cookies[settings.AUTH_COOKIE_ACCESS] = access
    api.cookies[settings.AUTH_COOKIE_REFRESH] = refresh
    return api


def future_date(days: int = 2):
    """Yakshanbaga tushib qolmasligi uchun ish kunini qaytaradi."""
    day = timezone.localdate() + timedelta(days=days)
    return day
