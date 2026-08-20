from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.salons.models import BarberDayOff, BarberSchedule

from .factories import auth_client, make_barber, make_client_user, make_superadmin


class BookingCreateTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.client_user = make_client_user()
        self.api = auth_client(self.client_user)
        self.date = timezone.localdate() + timedelta(days=2)

    def _payload(self, at="14:00", service="Soch olish"):
        return {
            "barber": str(self.barber.id),
            "booking_date": self.date.isoformat(),
            "booking_time": at,
            "service_name": service,
        }

    def test_create_booking_takes_price_from_barber_services(self):
        response = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["price"], 50000)
        self.assertEqual(response.data["duration_minutes"], 30)
        self.assertEqual(response.data["status"], "pending")

    def test_client_cannot_dictate_price(self):
        payload = self._payload() | {"price": 1, "duration_minutes": 5}
        response = self.api.post("/api/v1/bookings/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.get().price, 50000)

    def test_unknown_service_rejected(self):
        response = self.api.post("/api/v1/bookings/", self._payload(service="Tatuirovka"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("service_name", response.data["errors"])

    def test_double_booking_same_slot_is_conflict(self):
        self.assertEqual(self.api.post("/api/v1/bookings/", self._payload(), format="json").status_code, 201)

        other = auth_client(make_client_user(phone="+998907000002", name="Ikkinchi"))
        response = other.post("/api/v1/bookings/", self._payload(), format="json")

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "slot_taken")
        self.assertEqual(Booking.objects.count(), 1)

    def test_overlapping_longer_service_is_conflict(self):
        """14:00 dagi 60 daqiqalik xizmat 14:30 ni ham egallaydi."""
        self.api.post("/api/v1/bookings/", self._payload(service="Soqol olish"), format="json")

        other = auth_client(make_client_user(phone="+998907000003", name="Uchinchi"))
        response = other.post("/api/v1/bookings/", self._payload(at="14:30"), format="json")

        self.assertEqual(response.status_code, 409, response.data)

    def test_cancelled_slot_can_be_rebooked(self):
        first = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        booking_id = first.data["id"]
        self.api.post(f"/api/v1/bookings/{booking_id}/cancel/", {"reason": "Fikrim o'zgardi"}, format="json")

        other = auth_client(make_client_user(phone="+998907000004", name="To'rtinchi"))
        response = other.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_time_must_match_slot_grid(self):
        response = self.api.post("/api/v1/bookings/", self._payload(at="14:17"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("booking_time", response.data["errors"])

    def test_outside_working_hours_rejected(self):
        response = self.api.post("/api/v1/bookings/", self._payload(at="22:00"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_past_date_rejected(self):
        self.date = timezone.localdate() - timedelta(days=1)
        response = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_too_far_ahead_rejected(self):
        self.date = timezone.localdate() + timedelta(days=365)
        response = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_day_off_rejected(self):
        BarberDayOff.objects.create(barber=self.barber, date=self.date)
        response = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_non_working_weekday_rejected(self):
        BarberSchedule.objects.filter(barber=self.barber, weekday=self.date.weekday()).update(
            is_working=False
        )
        response = self.api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_barber_cannot_create_booking(self):
        api = auth_client(self.barber.profile)
        response = api.post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_create_booking(self):
        from rest_framework.test import APIClient

        response = APIClient().post("/api/v1/bookings/", self._payload(), format="json")
        self.assertEqual(response.status_code, 401)


class BookingLifecycleTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.client_user = make_client_user()
        self.date = timezone.localdate() + timedelta(days=3)
        self.booking = Booking.objects.create(
            client=self.client_user,
            barber=self.barber,
            salon=self.barber.salon,
            booking_date=self.date,
            booking_time=time(11, 0),
            service_name="Soch olish",
            price=50000,
            duration_minutes=30,
        )
        self.barber_api = auth_client(self.barber.profile)
        self.client_api = auth_client(self.client_user)

    def test_barber_confirms_then_completes(self):
        response = self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "confirmed")

        response = self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/complete/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "completed")

        self.barber.refresh_from_db()
        self.assertEqual(self.barber.completed_bookings, 1)

    def test_client_cannot_confirm(self):
        response = self.client_api.post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        self.assertEqual(response.status_code, 403)

    def test_other_barber_cannot_touch_booking(self):
        stranger = make_barber(phone="+998901000099", name="Begona usta")
        response = auth_client(stranger.profile).post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        self.assertEqual(response.status_code, 404)  # ro'yxatda ko'rinmaydi

    def test_client_cannot_cancel_within_window(self):
        soon = timezone.localtime() + timedelta(minutes=30)
        self.booking.booking_date = soon.date()
        self.booking.booking_time = soon.time().replace(second=0, microsecond=0)
        self.booking.save()

        response = self.client_api.post(f"/api/v1/bookings/{self.booking.id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_confirm_twice_fails(self):
        self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        response = self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        self.assertEqual(response.status_code, 400)


class BookingVisibilityTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.mine = make_client_user()
        self.other = make_client_user(phone="+998907000005", name="Boshqa")
        for client_user, at in ((self.mine, time(10, 0)), (self.other, time(11, 0))):
            Booking.objects.create(
                client=client_user,
                barber=self.barber,
                booking_date=timezone.localdate() + timedelta(days=1),
                booking_time=at,
                service_name="Soch olish",
                price=50000,
            )

    def test_client_sees_only_own_bookings(self):
        response = auth_client(self.mine).get("/api/v1/bookings/")
        self.assertEqual(response.data["count"], 1)

    def test_barber_sees_all_their_bookings(self):
        response = auth_client(self.barber.profile).get("/api/v1/bookings/")
        self.assertEqual(response.data["count"], 2)

    def test_superadmin_sees_everything(self):
        response = auth_client(make_superadmin()).get("/api/v1/bookings/")
        self.assertEqual(response.data["count"], 2)


class AvailabilityTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.date = timezone.localdate() + timedelta(days=2)

    def test_slots_listed_for_working_day(self):
        response = self.client.get(
            f"/api/v1/barbers/{self.barber.id}/available-slots/", {"date": self.date.isoformat()}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_working_day"])
        # 09:00–20:00, 30 daqiqa → 22 ta slot
        self.assertEqual(len(response.data["slots"]), 22)
        self.assertTrue(all(s["is_available"] for s in response.data["slots"]))

    def test_booked_slot_marked_unavailable(self):
        Booking.objects.create(
            client=make_client_user(),
            barber=self.barber,
            booking_date=self.date,
            booking_time=time(12, 0),
            service_name="Soch olish",
            price=50000,
            duration_minutes=30,
        )
        response = self.client.get(
            f"/api/v1/barbers/{self.barber.id}/available-slots/", {"date": self.date.isoformat()}
        )
        slot = next(s for s in response.data["slots"] if s["time"] == "12:00")
        self.assertFalse(slot["is_available"])
        self.assertEqual(slot["reason"], "booked")

    def test_break_slots_excluded(self):
        BarberSchedule.objects.filter(barber=self.barber).update(
            break_start=time(13, 0), break_end=time(14, 0)
        )
        response = self.client.get(
            f"/api/v1/barbers/{self.barber.id}/available-slots/", {"date": self.date.isoformat()}
        )
        blocked = [s["time"] for s in response.data["slots"] if s["reason"] == "break"]
        self.assertEqual(blocked, ["13:00", "13:30"])

    def test_day_off_returns_empty(self):
        BarberDayOff.objects.create(barber=self.barber, date=self.date)
        response = self.client.get(
            f"/api/v1/barbers/{self.barber.id}/available-slots/", {"date": self.date.isoformat()}
        )
        self.assertFalse(response.data["is_working_day"])
        self.assertEqual(response.data["slots"], [])

    def test_date_parameter_required(self):
        response = self.client.get(f"/api/v1/barbers/{self.barber.id}/available-slots/")
        self.assertEqual(response.status_code, 400)

    def test_service_duration_changes_slot_count(self):
        response = self.client.get(
            f"/api/v1/barbers/{self.barber.id}/available-slots/",
            {"date": self.date.isoformat(), "service": "Soqol olish"},  # 60 daqiqa
        )
        self.assertEqual(len(response.data["slots"]), 21)
