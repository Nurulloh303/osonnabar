"""Cookie'dan JWT o'qiydigan autentifikatsiya klassi.

Ustuvorlik:
  1. `Authorization: Bearer <token>` — Swagger / mobil ilova / server-to-server uchun.
  2. `on_access` httpOnly cookie — Next.js frontend uchun (asosiy yo'l).

Cookie orqali kelgan so'rovlarda CSRF majburiy tekshiriladi, chunki brauzer
cookie'ni avtomatik yuboradi (SameSite=None bo'lganda bu yagona himoya).
"""

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication


class _CSRFCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)

        if header is not None:
            raw_token = self.get_raw_token(header)
            from_cookie = False
        else:
            raw_token = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS)
            from_cookie = True

        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        if from_cookie and request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            self.enforce_csrf(request)

        return user, validated_token

    def enforce_csrf(self, request):
        check = _CSRFCheck(lambda req: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(_("CSRF tekshiruvi o'tmadi: %s") % reason)
