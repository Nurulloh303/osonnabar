"""Google Sign-In: frontend `id_token` yuboradi, backend uni tekshiradi.

Next.js tomonida `@react-oauth/google` yoki NextAuth ishlatilib, olingan
`credential` (JWT) shu yerga POST qilinadi.
"""

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework.exceptions import AuthenticationFailed

ALLOWED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_id_token(token: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise AuthenticationFailed("GOOGLE_CLIENT_ID sozlanmagan.")

    try:
        payload = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise AuthenticationFailed(f"Google token yaroqsiz: {exc}") from exc

    if payload.get("iss") not in ALLOWED_ISSUERS:
        raise AuthenticationFailed("Google token issuer noto'g'ri.")
    if not payload.get("email_verified", False):
        raise AuthenticationFailed("Google akkaunt emaili tasdiqlanmagan.")

    return {
        "sub": payload["sub"],
        "email": payload.get("email"),
        "full_name": payload.get("name") or "",
        "picture": payload.get("picture") or "",
    }
