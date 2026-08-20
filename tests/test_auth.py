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


@override_settings(OTP_RETURN_IN_RESPONSE=True, DEBUG=True, SMS_BACKEND="console")
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
