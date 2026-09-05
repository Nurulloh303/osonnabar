from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatus
from apps.salons.models import Barber, BarberSchedule

from .factories import (
    auth_client,
    make_barber,
    make_client_user,
    make_image,
    make_superadmin,
)


class BarberPanelTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.api = auth_client(self.barber.profile)
        self.client_user = make_client_user()

        today = timezone.localdate()
        for offset, status in ((-2, BookingStatus.COMPLETED), (-1, BookingStatus.COMPLETED), (1, BookingStatus.PENDING)):
            Booking.objects.create(
                client=self.client_user,
                barber=self.barber,
                salon=self.barber.salon,
                booking_date=today + timedelta(days=offset),
                booking_time=time(10 + offset % 3, 0),
                service_name="Soch olish",
                price=50000,
                status=status,
            )

    def test_stats_aggregates_revenue(self):
        response = self.api.get("/api/v1/barber/me/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["completed"], 2)
        self.assertEqual(response.data["totals"]["revenue_total"], 100000)
        self.assertEqual(response.data["totals"]["pending"], 1)
        self.assertEqual(len(response.data["chart"]), 30)

    def test_client_cannot_open_barber_stats(self):
        response = auth_client(self.client_user).get("/api/v1/barber/me/stats/")
        self.assertEqual(response.status_code, 403)

    def test_barber_updates_own_profile(self):
        response = self.api.patch(
            "/api/v1/barber/me/",
            {"bio": "Yangi tavsif", "services": [{"name": "Soch olish", "price": 60000}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.barber.refresh_from_db()
        self.assertEqual(self.barber.services[0]["price"], 60000)

    def test_barber_uploads_own_photo(self):
        """Usta o'z rasmini `multipart/form-data` bilan yuklaydi.

        `services` majburiy emas, shuning uchun faqat rasm yuborish yetarli.
        """
        response = self.api.patch(
            "/api/v1/barber/me/", {"avatar": make_image()}, format="multipart"
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.barber.refresh_from_db()
        self.assertTrue(self.barber.avatar.name.startswith("barbers/"))

    def test_uploaded_photo_appears_in_public_list(self):
        """Xaritadagi belgi va kartochka shu maydondan rasm oladi."""
        self.api.patch("/api/v1/barber/me/", {"avatar": make_image()}, format="multipart")

        response = APIClient().get("/api/v1/barbers/")
        row = next(r for r in response.data["results"] if r["id"] == str(self.barber.id))
        self.assertIsNotNone(row["avatar"])
        self.assertTrue(row["avatar"].startswith("http"))  # to'liq URL qaytadi

    def test_non_image_file_rejected(self):
        fake = SimpleUploadedFile("zararli.html", b"<script>alert(1)</script>", "text/html")
        response = self.api.patch("/api/v1/barber/me/", {"avatar": fake}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_duplicate_service_names_rejected(self):
        response = self.api.patch(
            "/api/v1/barber/me/",
            {"services": [{"name": "Soch olish", "price": 1000}, {"name": "soch olish", "price": 2000}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_bulk_schedule_update(self):
        payload = [
            {
                "weekday": day,
                "is_working": day < 5,
                "start_time": "10:00",
                "end_time": "19:00",
                "slot_minutes": 60,
            }
            for day in range(7)
        ]
        response = self.api.put("/api/v1/barber/me/schedule/bulk/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        schedule = BarberSchedule.objects.get(barber=self.barber, weekday=6)
        self.assertFalse(schedule.is_working)
        self.assertEqual(schedule.slot_minutes, 60)

    def test_schedule_end_before_start_rejected(self):
        response = self.api.put(
            "/api/v1/barber/me/schedule/bulk/",
            [{"weekday": 0, "start_time": "18:00", "end_time": "09:00"}],
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_day_off_blocked_when_active_bookings_exist(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        response = self.api.post("/api/v1/barber/me/days-off/", {"date": tomorrow.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_day_off_created_on_free_day(self):
        free_day = timezone.localdate() + timedelta(days=9)
        response = self.api.post("/api/v1/barber/me/days-off/", {"date": free_day.isoformat()}, format="json")
        self.assertEqual(response.status_code, 201, response.data)


class SuperAdminPanelTests(TestCase):
    def setUp(self):
        self.admin = make_superadmin()
        self.api = auth_client(self.admin)
        self.barber = make_barber()
        self.client_user = make_client_user()

        Booking.objects.create(
            client=self.client_user,
            barber=self.barber,
            salon=self.barber.salon,
            booking_date=timezone.localdate() - timedelta(days=1),
            booking_time=time(12, 0),
            service_name="Soch olish",
            price=50000,
            status=BookingStatus.COMPLETED,
        )

    def test_platform_stats(self):
        response = self.api.get("/api/v1/super-admin/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["users"]["clients"], 1)
        self.assertEqual(response.data["barbers"]["active"], 1)
        self.assertEqual(response.data["bookings"]["revenue_total"], 50000)
        self.assertEqual(len(response.data["top_barbers"]), 1)

    def test_stats_forbidden_for_client(self):
        response = auth_client(self.client_user).get("/api/v1/super-admin/stats/")
        self.assertEqual(response.status_code, 403)

    def test_stats_unauthorized_for_anonymous(self):
        response = APIClient().get("/api/v1/super-admin/stats/")
        self.assertEqual(response.status_code, 401)

    def test_user_list_with_spend(self):
        response = self.api.get("/api/v1/super-admin/users/", {"role": "client"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["total_spent"], 50000)

    def test_block_user_also_blocks_barber_profile(self):
        response = self.api.post(f"/api/v1/super-admin/users/{self.barber.profile_id}/block/")
        self.assertEqual(response.status_code, 200)

        self.barber.refresh_from_db()
        self.assertEqual(self.barber.status, Barber.Status.BLOCKED)
        self.assertFalse(response.data["is_active"])

    def test_cannot_block_superadmin(self):
        response = self.api.post(f"/api/v1/super-admin/users/{self.admin.id}/block/")
        self.assertEqual(response.status_code, 400)

    def test_create_barber_with_profile(self):
        response = self.api.post(
            "/api/v1/super-admin/barbers/",
            {
                "email": "yangi.usta@gmail.com",
                "phone": "901239999",
                "full_name": "Yangi Usta",
                "specialty": "men",
                "services": [{"name": "Soch olish", "price": 45000, "duration_minutes": 30}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        barber = Barber.objects.get(profile__email="yangi.usta@gmail.com")
        self.assertEqual(barber.profile.role, "barber")
        self.assertEqual(barber.profile.phone, "+998901239999")
        self.assertEqual(barber.services[0]["price"], 45000)

    def test_create_barber_requires_email(self):
        """Email — ustaning Google orqali kirish yo'li, usiz u tizimga kira olmaydi."""
        response = self.api.post(
            "/api/v1/super-admin/barbers/",
            {"phone": "901239998", "full_name": "Emailsiz Usta"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data["errors"])

    def test_create_barber_without_phone_is_allowed(self):
        """Telefon ixtiyoriy — Google akkaunti yetarli."""
        response = self.api.post(
            "/api/v1/super-admin/barbers/",
            {"email": "telefonsiz@gmail.com", "full_name": "Telefonsiz Usta"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        barber = Barber.objects.get(profile__email="telefonsiz@gmail.com")
        self.assertIsNone(barber.profile.phone)

    def test_existing_client_promoted_to_barber_keeps_account(self):
        """Google orqali kirgan mijozni usta qilib tayinlash — yangi akkaunt ochilmasin."""
        User = get_user_model()
        existing = User.objects.create_user(
            email="mijoz@gmail.com", full_name="Mijoz", google_sub="sub-abc"
        )
        response = self.api.post(
            "/api/v1/super-admin/barbers/",
            {"email": "mijoz@gmail.com", "full_name": "Mijoz"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        existing.refresh_from_db()
        self.assertEqual(existing.role, "barber")
        self.assertEqual(existing.google_sub, "sub-abc")  # Google bog'lanishi saqlanadi
        self.assertEqual(User.objects.filter(email="mijoz@gmail.com").count(), 1)

    def test_block_and_activate_barber(self):
        self.api.post(f"/api/v1/super-admin/barbers/{self.barber.id}/block/")
        self.barber.refresh_from_db()
        self.assertEqual(self.barber.status, Barber.Status.BLOCKED)

        self.api.post(f"/api/v1/super-admin/barbers/{self.barber.id}/activate/")
        self.barber.refresh_from_db()
        self.assertEqual(self.barber.status, Barber.Status.ACTIVE)

    def test_barber_cannot_reach_admin_endpoints(self):
        response = auth_client(self.barber.profile).get("/api/v1/super-admin/users/")
        self.assertEqual(response.status_code, 403)


class SchemaTests(TestCase):
    def test_openapi_schema_builds(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)

    def test_health(self):
        self.assertEqual(self.client.get("/health/").status_code, 200)
