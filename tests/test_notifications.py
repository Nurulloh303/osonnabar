"""Web Push va sayt ichidagi xabarnomalar."""

from datetime import time, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import Notification, NotificationKind, PushSubscription

from .factories import auth_client, future_date, make_barber, make_client_user

SUBSCRIPTION = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
    "keys": {"p256dh": "BPZx1fhyWcVhfY-key", "auth": "authsecret123"},
    "expirationTime": None,
}


# Push'ni sinxron yuboramiz — testda oqim kutib o'tirmaslik uchun.
@override_settings(PUSH_SEND_ASYNC=False)
class PushSubscriptionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_client_user()
        self.api = auth_client(self.user)

    def test_subscribe_saves_endpoint_and_keys(self):
        response = self.api.post(
            "/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.user, self.user)
        self.assertEqual(subscription.endpoint, SUBSCRIPTION["endpoint"])
        self.assertEqual(subscription.auth_keys, SUBSCRIPTION["keys"])

    def test_subscribe_twice_updates_instead_of_duplicating(self):
        self.api.post("/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json")
        self.api.post("/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_same_browser_new_user_takes_over_subscription(self):
        """Boshqa mijoz shu brauzerda kirsa — obuna unga o'tishi kerak.

        Aks holda eski egasi begona qurilmaga xabar olib turardi.
        """
        self.api.post("/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json")

        other = make_client_user(phone="+998907000099", name="Boshqa Mijoz")
        auth_client(other).post(
            "/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json"
        )

        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertEqual(PushSubscription.objects.get().user, other)

    def test_one_user_can_have_several_devices(self):
        self.api.post("/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json")
        phone = dict(SUBSCRIPTION, endpoint="https://fcm.googleapis.com/fcm/send/phone999")
        self.api.post("/api/v1/notifications/subscribe/", phone, format="json")
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 2)

    def test_missing_keys_rejected(self):
        broken = {"endpoint": SUBSCRIPTION["endpoint"], "keys": {"p256dh": "only-one"}}
        response = self.api.post("/api/v1/notifications/subscribe/", broken, format="json")
        self.assertEqual(response.status_code, 400)

    def test_http_endpoint_rejected(self):
        insecure = dict(SUBSCRIPTION, endpoint="http://fcm.googleapis.com/fcm/send/x")
        response = self.api.post("/api/v1/notifications/subscribe/", insecure, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unsubscribe_removes_row(self):
        self.api.post("/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json")
        response = self.api.post(
            "/api/v1/notifications/unsubscribe/",
            {"endpoint": SUBSCRIPTION["endpoint"]},
            format="json",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_anonymous_cannot_subscribe(self):
        response = APIClient().post(
            "/api/v1/notifications/subscribe/", SUBSCRIPTION, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_vapid_key_is_public(self):
        with override_settings(VAPID_PUBLIC_KEY="test-public", VAPID_PRIVATE_KEY="test-private"):
            response = APIClient().get("/api/v1/notifications/vapid-key/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["public_key"], "test-public")
        self.assertTrue(response.data["configured"])


@override_settings(PUSH_SEND_ASYNC=False)
class NotificationListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_client_user()
        self.api = auth_client(self.user)
        self.other = make_client_user(phone="+998907000098", name="Begona")

        for index in range(3):
            Notification.objects.create(
                user=self.user, title=f"Xabar {index}", body="matn", kind=NotificationKind.SYSTEM
            )
        Notification.objects.create(user=self.other, title="Begona xabar", body="matn")

    def test_list_returns_only_own_notifications(self):
        response = self.api.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        titles = {row["title"] for row in response.data["results"]}
        self.assertNotIn("Begona xabar", titles)

    def test_unread_count(self):
        response = self.api.get("/api/v1/notifications/unread-count/")
        self.assertEqual(response.data["unread"], 3)

    def test_mark_all_read(self):
        response = self.api.put("/api/v1/notifications/read/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread"], 0)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)
        # Begonaniki tegilmagan bo'lishi kerak
        self.assertTrue(Notification.objects.get(user=self.other).is_read is False)

    def test_mark_selected_read(self):
        target = Notification.objects.filter(user=self.user).first()
        response = self.api.put(
            "/api/v1/notifications/read/", {"ids": [str(target.id)]}, format="json"
        )
        self.assertEqual(response.data["unread"], 2)
        target.refresh_from_db()
        self.assertTrue(target.is_read)

    def test_cannot_mark_someone_elses_notification(self):
        foreign = Notification.objects.get(user=self.other)
        self.api.put("/api/v1/notifications/read/", {"ids": [str(foreign.id)]}, format="json")
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_read)

    def test_filter_unread(self):
        Notification.objects.filter(user=self.user).update(is_read=True)
        unread = Notification.objects.filter(user=self.user).first()
        Notification.objects.filter(pk=unread.pk).update(is_read=False)

        response = self.api.get("/api/v1/notifications/?is_read=false")
        self.assertEqual(response.data["count"], 1)


@override_settings(PUSH_SEND_ASYNC=False)
class BookingEventNotificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_user = make_client_user()
        self.barber = make_barber()
        self.barber_api = auth_client(self.barber.profile)
        self.client_api = auth_client(self.client_user)

        self.booking = Booking.objects.create(
            client=self.client_user,
            barber=self.barber,
            salon=self.barber.salon,
            booking_date=future_date(),
            booking_time=time(11, 0),
            duration_minutes=30,
            service_name="Soch olish",
            price=50000,
        )

    def _client_notifications(self):
        return Notification.objects.filter(user=self.client_user)

    def test_confirm_notifies_client(self):
        response = self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/confirm/")
        self.assertEqual(response.status_code, 200, response.data)

        notification = self._client_notifications().get(kind=NotificationKind.BOOKING_CONFIRMED)
        self.assertIn("tasdiqlandi", notification.title.lower())
        self.assertEqual(notification.booking_id, self.booking.id)

    def test_barber_cancel_notifies_client(self):
        self.barber_api.post(
            f"/api/v1/bookings/{self.booking.id}/cancel/", {"reason": "Kasal bo'lib qoldim"},
            format="json",
        )
        notification = self._client_notifications().get(kind=NotificationKind.BOOKING_CANCELLED)
        self.assertIn("Kasal", notification.body)

    def test_client_cancelling_own_booking_does_not_notify_self(self):
        """Mijoz o'zi bekor qilgan bo'lsa, unga xabar bermaymiz — u allaqachon biladi."""
        self.client_api.post(f"/api/v1/bookings/{self.booking.id}/cancel/", {}, format="json")
        self.assertFalse(
            self._client_notifications().filter(kind=NotificationKind.BOOKING_CANCELLED).exists()
        )

    def test_new_booking_notifies_barber(self):
        response = self.client_api.post(
            "/api/v1/bookings/",
            {
                "barber": str(self.barber.id),
                "booking_date": future_date(3).isoformat(),
                "booking_time": "15:00",
                "service_name": "Soch olish",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            Notification.objects.filter(
                user=self.barber.profile, kind=NotificationKind.BOOKING_CREATED
            ).exists()
        )

    def test_complete_notifies_client(self):
        self.barber_api.post(f"/api/v1/bookings/{self.booking.id}/complete/")
        self.assertTrue(
            self._client_notifications().filter(kind=NotificationKind.BOOKING_COMPLETED).exists()
        )


@override_settings(PUSH_SEND_ASYNC=False)
class BookingReminderCronTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_user = make_client_user()
        self.barber = make_barber()

    def _booking_in(self, minutes: int, status=BookingStatus.CONFIRMED) -> Booking:
        starts_at = timezone.localtime() + timedelta(minutes=minutes)
        return Booking.objects.create(
            client=self.client_user,
            barber=self.barber,
            salon=self.barber.salon,
            booking_date=starts_at.date(),
            booking_time=starts_at.time().replace(second=0, microsecond=0),
            duration_minutes=30,
            service_name="Soch olish",
            price=50000,
            status=status,
        )

    def test_reminder_sent_for_booking_in_one_hour(self):
        booking = self._booking_in(60)
        call_command("send_booking_reminders")

        self.assertTrue(
            Notification.objects.filter(
                user=self.client_user, kind=NotificationKind.BOOKING_REMINDER
            ).exists()
        )
        booking.refresh_from_db()
        self.assertIsNotNone(booking.reminder_sent_at)

    def test_reminder_is_not_sent_twice(self):
        """Cron oynalari ustma-ust tushsa ham ikkinchi eslatma ketmasligi kerak."""
        self._booking_in(60)
        call_command("send_booking_reminders")
        call_command("send_booking_reminders")

        self.assertEqual(
            Notification.objects.filter(kind=NotificationKind.BOOKING_REMINDER).count(), 1
        )

    def test_far_away_booking_is_ignored(self):
        self._booking_in(60 * 5)
        call_command("send_booking_reminders")
        self.assertFalse(Notification.objects.filter(kind=NotificationKind.BOOKING_REMINDER).exists())

    def test_pending_booking_is_ignored(self):
        """Faqat TASDIQLANGAN navbatlar eslatiladi."""
        self._booking_in(60, status=BookingStatus.PENDING)
        call_command("send_booking_reminders")
        self.assertFalse(Notification.objects.filter(kind=NotificationKind.BOOKING_REMINDER).exists())

    def test_dry_run_changes_nothing(self):
        booking = self._booking_in(60)
        call_command("send_booking_reminders", dry_run=True)

        self.assertFalse(Notification.objects.exists())
        booking.refresh_from_db()
        self.assertIsNone(booking.reminder_sent_at)


@override_settings(
    PUSH_SEND_ASYNC=False,
    PUSH_ENABLED=True,
    VAPID_PUBLIC_KEY="test-public",
    VAPID_PRIVATE_KEY="test-private",
)
class WebPushDeliveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_client_user()
        self.subscription = PushSubscription.objects.create(
            user=self.user, endpoint=SUBSCRIPTION["endpoint"], auth_keys=SUBSCRIPTION["keys"]
        )

    def test_push_is_sent_for_each_device(self):
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://fcm.googleapis.com/fcm/send/second-device",
            auth_keys=SUBSCRIPTION["keys"],
        )

        with patch("pywebpush.webpush") as webpush:
            from apps.notifications import services

            with self.captureOnCommitCallbacks(execute=True):
                services.notify(self.user, title="Salom", body="Matn")

        self.assertEqual(webpush.call_count, 2)

    def test_dead_subscription_is_deleted(self):
        """Push xizmati 410 qaytarsa — obuna o'lgan, saqlab o'tirishning ma'nosi yo'q."""
        from pywebpush import WebPushException

        class FakeResponse:
            status_code = 410

        with patch("pywebpush.webpush", side_effect=WebPushException("gone", FakeResponse())):
            from apps.notifications import services

            with self.captureOnCommitCallbacks(execute=True):
                services.notify(self.user, title="Salom", body="Matn")

        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_push_failure_does_not_lose_the_notification(self):
        """Push ishlamasa ham, sayt ichidagi xabar baribir saqlanishi kerak."""
        from pywebpush import WebPushException

        class FakeResponse:
            status_code = 500

        with patch("pywebpush.webpush", side_effect=WebPushException("boom", FakeResponse())):
            from apps.notifications import services

            with self.captureOnCommitCallbacks(execute=True):
                services.notify(self.user, title="Salom", body="Matn")

        notification = Notification.objects.get()
        self.assertEqual(notification.title, "Salom")
        self.assertIsNone(notification.push_sent_at)

    @override_settings(PUSH_ENABLED=False, VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_works_without_vapid_configured(self):
        """VAPID sozlanmagan bo'lsa push jimgina o'chadi, xato bermaydi."""
        with patch("pywebpush.webpush") as webpush:
            from apps.notifications import services

            with self.captureOnCommitCallbacks(execute=True):
                services.notify(self.user, title="Salom", body="Matn")

        webpush.assert_not_called()
        self.assertEqual(Notification.objects.count(), 1)
