from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatus
from apps.reviews.models import Review
from apps.salons.models import Barber, Salon, Specialty

from .factories import auth_client, make_barber, make_client_user, make_superadmin


class PublicCatalogTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.barber = make_barber()

    def test_salon_list_is_public(self):
        response = self.api.get("/api/v1/salons/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["barbers_count"], 1)

    def test_barber_list_exposes_price_from(self):
        response = self.api.get("/api/v1/barbers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["price_from"], 30000)

    def test_blocked_barber_hidden(self):
        self.barber.status = Barber.Status.BLOCKED
        self.barber.save()
        response = self.api.get("/api/v1/barbers/")
        self.assertEqual(response.data["count"], 0)

    def test_specialty_filter(self):
        make_barber(phone="+998901000002", name="Ayollar ustasi").__class__.objects.filter(
            profile__phone="+998901000002"
        ).update(specialty=Specialty.WOMEN)

        response = self.api.get("/api/v1/barbers/", {"specialty": "women"})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["specialty"], "women")

    def test_search_by_name(self):
        response = self.api.get("/api/v1/barbers/", {"search": "Test Usta"})
        self.assertEqual(response.data["count"], 1)

    def test_geo_distance_and_radius(self):
        far_salon = Salon.objects.create(
            name="Samarqand Salon", address="Samarqand", location_lat=39.6542, location_lng=66.9597
        )
        make_barber(phone="+998901000003", name="Uzoq usta", salon=far_salon)

        response = self.api.get("/api/v1/barbers/", {"lat": 41.3111, "lng": 69.2797, "radius": 20})
        self.assertEqual(response.data["count"], 1)
        self.assertIsNotNone(response.data["results"][0]["distance_km"])
        self.assertLess(response.data["results"][0]["distance_km"], 20)

    def test_barber_detail_includes_schedule(self):
        response = self.api.get(f"/api/v1/barbers/{self.barber.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["schedules"]), 7)


class ReviewTests(TestCase):
    def setUp(self):
        self.barber = make_barber()
        self.client_user = make_client_user()
        self.api = auth_client(self.client_user)
        self.booking = Booking.objects.create(
            client=self.client_user,
            barber=self.barber,
            salon=self.barber.salon,
            booking_date=timezone.localdate() - timedelta(days=1),
            booking_time="12:00",
            service_name="Soch olish",
            price=50000,
            status=BookingStatus.COMPLETED,
        )

    def test_review_updates_barber_rating(self):
        response = self.api.post(
            "/api/v1/reviews/",
            {"booking": str(self.booking.id), "rating": 5, "comment": "Zo'r!"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        self.barber.refresh_from_db()
        self.assertEqual(self.barber.rating_avg, 5.0)
        self.assertEqual(self.barber.reviews_count, 1)

        self.barber.salon.refresh_from_db()
        self.assertEqual(self.barber.salon.rating_avg, 5.0)

    def test_cannot_review_twice(self):
        payload = {"booking": str(self.booking.id), "rating": 5}
        self.api.post("/api/v1/reviews/", payload, format="json")
        response = self.api.post("/api/v1/reviews/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_cannot_review_unfinished_booking(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        response = self.api.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 5}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_review_someone_elses_booking(self):
        stranger = auth_client(make_client_user(phone="+998907000009", name="Begona"))
        response = stranger.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 1}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_rating_out_of_range_rejected(self):
        response = self.api.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 9}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_author_name_is_masked(self):
        self.api.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 4}, format="json"
        )
        response = APIClient().get("/api/v1/reviews/")
        self.assertEqual(response.data["results"][0]["client"]["full_name"], "Test M.")

    def test_barber_can_reply(self):
        create = self.api.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 4}, format="json"
        )
        review_id = create.data["id"]

        response = auth_client(self.barber.profile).post(
            f"/api/v1/reviews/{review_id}/reply/", {"barber_reply": "Rahmat!"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Review.objects.get().barber_reply, "Rahmat!")

    def test_review_deleted_recalculates_rating(self):
        create = self.api.post(
            "/api/v1/reviews/", {"booking": str(self.booking.id), "rating": 5}, format="json"
        )
        self.api.delete(f"/api/v1/reviews/{create.data['id']}/")

        self.barber.refresh_from_db()
        self.assertEqual(self.barber.reviews_count, 0)
        self.assertEqual(self.barber.rating_avg, 0)
