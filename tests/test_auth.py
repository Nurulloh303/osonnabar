from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import PhoneOTP
from apps.accounts.validators import normalize_phone

from .factories import auth_client, make_client_user

User = get_user_model()


class PhoneNormalizationTests(TestCase):
    def test_various_formats(self):
        for raw in ("901234567", "998901234567", "+998 90 123 45 67", "+998-90-123-45-67"):
            self.assertEqual(normalize_phone(raw), "+998901234567")

    def test_invalid_phone_rejected(self):
        from rest_framework.exceptions import ValidationError

        for raw in ("123", "+7 999 111 22 33", "9012345678901"):
            with self.assertRaises(ValidationError):
                normalize_phone(raw)


@override_settings(
    AUTH_SMS_ENABLED=True, OTP_RETURN_IN_RESPONSE=True, DEBUG=True, SMS_BACKEND="console"
)
class OTPFlowTests(TestCase):
    def setUp(self):
        # Throttle hisoblagichlari cache'da yashaydi va Django uni testlar orasida
        # tozalamaydi — tozalamasak, sinfdagi 6-chi `_request_code()` `otp_request`
        # limitiga (5/hour) urilib, aloqasi yo'q testni yiqitadi.
        cache.clear()
        self.api = APIClient()

    def _request_code(self, phone="+998901234567"):
        response = self.api.post("/api/v1/auth/otp/request/", {"phone": phone}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_request_and_verify_creates_user_and_sets_cookies(self):
        data = self._request_code()
        self.assertTrue(data["is_new_user"])

        code = PhoneOTP.objects.get(phone="+998901234567")
        self.assertNotEqual(code.code_hash, "0000")  # kod ochiq saqlanmaydi

        response = self.api.post(
            "/api/v1/auth/otp/verify/",
            {"phone": "901234567", "code": data["code"], "full_name": "Yangi Mijoz"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_new_user"])
        self.assertEqual(response.data["user"]["role"], "client")

        self.assertIn(settings.AUTH_COOKIE_ACCESS, response.cookies)
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_ACCESS]["httponly"])
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_REFRESH]["httponly"])

    def test_wrong_code_is_rejected_and_counted(self):
        self._request_code()
        response = self.api.post(
            "/api/v1/auth/otp/verify/", {"phone": "+998901234567", "code": "9999"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "otp_invalid")
        self.assertEqual(PhoneOTP.objects.get().attempts, 1)

    def test_resend_cooldown(self):
        self._request_code()
        response = self.api.post(
            "/api/v1/auth/otp/request/", {"phone": "+998901234567"}, format="json"
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "resend_cooldown")

    def test_expired_code_rejected(self):
        from datetime import timedelta

        from django.utils import timezone

        data = self._request_code()
        PhoneOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self.api.post(
            "/api/v1/auth/otp/verify/",
            {"phone": "+998901234567", "code": data["code"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "otp_expired")

    def test_blocked_user_cannot_login(self):
        user = make_client_user(phone="+998901234567")
        user.is_active = False
        user.save()

        data = self._request_code()
        response = self.api.post(
            "/api/v1/auth/otp/verify/", {"phone": "+998901234567", "code": data["code"]}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "account_blocked")


GOOGLE_INFO = {
    "sub": "google-sub-123456",
    "email": "mijoz@gmail.com",
    "full_name": "Google Mijoz",
    "picture": "",
}


@override_settings(GOOGLE_CLIENT_ID="test-client-id.apps.googleusercontent.com")
class GoogleAuthTests(TestCase):
    """Ro'yxatdan o'tishning asosiy yo'li — Google Sign-In."""

    def setUp(self):
        cache.clear()
        self.api = APIClient()

    def _login(self, info=None):
        with patch("apps.accounts.views.verify_google_id_token", return_value=info or GOOGLE_INFO):
            return self.api.post(
                "/api/v1/auth/google/", {"id_token": "soxta-token"}, format="json"
            )

    def test_first_login_creates_client_account(self):
        response = self._login()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_new_user"])
        self.assertEqual(response.data["user"]["email"], "mijoz@gmail.com")
        self.assertEqual(response.data["user"]["role"], "client")

        user = User.objects.get(email="mijoz@gmail.com")
        self.assertEqual(user.google_sub, "google-sub-123456")
        self.assertIsNone(user.phone)  # telefon so'ralmaydi

    def test_cookies_are_set(self):
        response = self._login()
        self.assertIn(settings.AUTH_COOKIE_ACCESS, response.cookies)
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_ACCESS]["httponly"])

    def test_second_login_reuses_same_account(self):
        self._login()
        response = self._login()
        self.assertFalse(response.data["is_new_user"])
        self.assertEqual(User.objects.filter(email="mijoz@gmail.com").count(), 1)

    def test_admin_created_barber_keeps_role_after_google_login(self):
        """Admin ustani email bilan yaratadi; usta Google orqali kirganda roli saqlanadi.

        Bu buzilsa — usta har kirganda oddiy mijoz bo'lib qolardi va o'z paneliga
        kira olmasdi.
        """
        User.objects.create_user(
            email="usta@gmail.com", full_name="Usta", role=User.Role.BARBER
        )
        info = dict(GOOGLE_INFO, email="usta@gmail.com", sub="usta-sub-999")
        response = self._login(info)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["is_new_user"])
        self.assertEqual(response.data["user"]["role"], "barber")
        self.assertEqual(User.objects.filter(email="usta@gmail.com").count(), 1)

    def test_blocked_account_cannot_login(self):
        User.objects.create_user(
            email="bloklangan@gmail.com", full_name="X", is_active=False
        )
        info = dict(GOOGLE_INFO, email="bloklangan@gmail.com", sub="blocked-sub")
        response = self._login(info)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "account_blocked")

    def test_google_without_email_is_rejected(self):
        info = dict(GOOGLE_INFO, email=None)
        response = self._login(info)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "google_no_email")

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_unconfigured_google_returns_error(self):
        response = self.api.post("/api/v1/auth/google/", {"id_token": "x"}, format="json")
        # DRF `AuthenticationFailed` ni 403 ga aylantiradi, chunki bu view'da
        # authenticator yo'q (WWW-Authenticate header'i bo'lmaydi).
        self.assertIn(response.status_code, (401, 403))


class AuthMethodsTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(GOOGLE_CLIENT_ID="abc.apps.googleusercontent.com", AUTH_SMS_ENABLED=False)
    def test_reports_google_only(self):
        response = APIClient().get("/api/v1/auth/methods/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["google"])
        self.assertFalse(response.data["sms"])
        self.assertEqual(response.data["google_client_id"], "abc.apps.googleusercontent.com")

    def test_available_without_login(self):
        self.assertEqual(APIClient().get("/api/v1/auth/methods/").status_code, 200)


class SMSDisabledTests(TestCase):
    """SMS o'chirilganda (standart holat) OTP manzillari umuman bo'lmasligi kerak."""

    def test_otp_endpoints_are_gone(self):
        api = APIClient()
        self.assertEqual(
            api.post("/api/v1/auth/otp/request/", {"phone": "+998901234567"}, format="json").status_code,
            404,
        )
        self.assertEqual(
            api.post(
                "/api/v1/auth/otp/verify/", {"phone": "+998901234567", "code": "1234"}, format="json"
            ).status_code,
            404,
        )

    def test_google_endpoint_still_exists(self):
        # 400/401 bo'lishi mumkin, lekin 404 EMAS — manzil ro'yxatda turishi kerak.
        response = APIClient().post("/api/v1/auth/google/", {"id_token": "x"}, format="json")
        self.assertNotEqual(response.status_code, 404)


class SessionTests(TestCase):
    def test_me_requires_auth(self):
        response = APIClient().get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_me_returns_profile(self):
        user = make_client_user()
        response = auth_client(user).get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["phone"], user.phone)
        self.assertFalse(response.data["barber_id"])

    def test_refresh_issues_new_access_cookie(self):
        user = make_client_user()
        api = auth_client(user)
        response = api.post("/api/v1/auth/refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.AUTH_COOKIE_ACCESS, response.cookies)

    def test_refresh_without_cookie_is_401(self):
        response = APIClient().post("/api/v1/auth/refresh/")
        self.assertEqual(response.status_code, 401)

    def test_logout_clears_cookies(self):
        api = auth_client(make_client_user())
        response = api.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[settings.AUTH_COOKIE_ACCESS].value, "")
