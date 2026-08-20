"""SMS shlyuzlari. Yangisini qo'shish = shu yerga bitta klass + settings.SMS_BACKENDS ga qator."""

import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("apps.accounts.sms")

TIMEOUT = 15


class SMSError(Exception):
    """Shlyuz xatosi — foydalanuvchiga 503 qaytariladi."""


class BaseSMSBackend:
    name = "base"

    def send(self, phone: str, text: str) -> dict:  # pragma: no cover - interfeys
        raise NotImplementedError


class ConsoleSMSBackend(BaseSMSBackend):
    """Development uchun: SMS o'rniga logga yozadi."""

    name = "console"

    def send(self, phone: str, text: str) -> dict:
        logger.warning("📱 SMS → %s : %s", phone, text)
        return {"provider": self.name, "status": "logged"}


class EskizSMSBackend(BaseSMSBackend):
    """Eskiz.uz (notify.eskiz.uz). Token 29 kun amal qiladi — cache'da saqlanadi."""

    name = "eskiz"
    TOKEN_CACHE_KEY = "eskiz:token"
    TOKEN_TTL = 60 * 60 * 24 * 20

    def _login(self) -> str:
        if not settings.ESKIZ_EMAIL or not settings.ESKIZ_PASSWORD:
            raise SMSError("ESKIZ_EMAIL / ESKIZ_PASSWORD sozlanmagan.")
        try:
            resp = requests.post(
                f"{settings.ESKIZ_BASE_URL}/auth/login",
                data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SMSError(f"Eskiz'ga ulanib bo'lmadi: {exc}") from exc

        if resp.status_code != 200:
            raise SMSError(f"Eskiz login xatosi: {resp.status_code} {resp.text[:200]}")

        token = (resp.json().get("data") or {}).get("token")
        if not token:
            raise SMSError("Eskiz token qaytarmadi.")
        cache.set(self.TOKEN_CACHE_KEY, token, self.TOKEN_TTL)
        return token

    def _token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            cache.delete(self.TOKEN_CACHE_KEY)
        return cache.get(self.TOKEN_CACHE_KEY) or self._login()

    def send(self, phone: str, text: str) -> dict:
        payload = {
            "mobile_phone": phone.lstrip("+"),
            "message": text,
            "from": settings.ESKIZ_FROM,
        }
        for attempt in (1, 2):  # 401 bo'lsa tokenni yangilab, bir marta qayta uriniladi
            token = self._token(force_refresh=attempt == 2)
            try:
                resp = requests.post(
                    f"{settings.ESKIZ_BASE_URL}/message/sms/send",
                    data=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                )
            except requests.RequestException as exc:
                raise SMSError(f"Eskiz'ga ulanib bo'lmadi: {exc}") from exc

            if resp.status_code == 401 and attempt == 1:
                continue
            if resp.status_code not in (200, 201):
                raise SMSError(f"Eskiz xatosi: {resp.status_code} {resp.text[:200]}")
            return {"provider": self.name, "response": resp.json()}
        raise SMSError("Eskiz avtorizatsiyasi muvaffaqiyatsiz.")


class PlaymobileSMSBackend(BaseSMSBackend):
    """Play Mobile (playmobile.uz) — HTTP Basic auth + JSON."""

    name = "playmobile"

    def send(self, phone: str, text: str) -> dict:
        if not settings.PLAYMOBILE_LOGIN or not settings.PLAYMOBILE_PASSWORD:
            raise SMSError("PLAYMOBILE_LOGIN / PLAYMOBILE_PASSWORD sozlanmagan.")

        message_id = f"osonnavbat-{phone.lstrip('+')}-{int(time.time())}"
        payload = {
            "messages": [
                {
                    "recipient": phone.lstrip("+"),
                    "message-id": message_id,
                    "sms": {
                        "originator": settings.PLAYMOBILE_FROM,
                        "content": {"text": text},
                    },
                }
            ]
        }
        try:
            resp = requests.post(
                f"{settings.PLAYMOBILE_BASE_URL}/send",
                json=payload,
                auth=(settings.PLAYMOBILE_LOGIN, settings.PLAYMOBILE_PASSWORD),
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise SMSError(f"Playmobile'ga ulanib bo'lmadi: {exc}") from exc

        if resp.status_code != 200:
            raise SMSError(f"Playmobile xatosi: {resp.status_code} {resp.text[:200]}")
        return {"provider": self.name, "message_id": message_id}
