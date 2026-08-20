"""JWT tokenlarni httpOnly cookie'ga yozish/o'chirish."""

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def issue_tokens(user) -> tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["phone"] = user.phone or ""
    access = refresh.access_token
    access["role"] = user.role
    access["phone"] = user.phone or ""
    return str(access), str(refresh)


def _common_kwargs() -> dict:
    return {
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN,
        "path": settings.AUTH_COOKIE_PATH,
        "httponly": True,
    }


def set_auth_cookies(response, access: str, refresh: str | None = None):
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS,
        access,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        **_common_kwargs(),
    )
    if refresh is not None:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH,
            refresh,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            **_common_kwargs(),
        )
    return response


def clear_auth_cookies(response):
    for name in (settings.AUTH_COOKIE_ACCESS, settings.AUTH_COOKIE_REFRESH):
        response.delete_cookie(
            name,
            path=settings.AUTH_COOKIE_PATH,
            domain=settings.AUTH_COOKIE_DOMAIN,
            samesite=settings.AUTH_COOKIE_SAMESITE,
        )
    return response
