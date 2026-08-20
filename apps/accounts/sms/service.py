from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from .backends import SMSError  # noqa: F401  (tashqariga re-export)

OTP_TEMPLATE = "osonNavbat: tasdiqlash kodi {code}. Kodni hech kimga aytmang."


@lru_cache(maxsize=4)
def _load(path: str):
    return import_string(path)()


def get_sms_backend():
    path = settings.SMS_BACKENDS.get(settings.SMS_BACKEND)
    if not path:
        raise SMSError(
            f"SMS_BACKEND='{settings.SMS_BACKEND}' noma'lum. "
            f"Mavjudlari: {', '.join(settings.SMS_BACKENDS)}"
        )
    return _load(path)


def send_otp_sms(phone: str, code: str) -> dict:
    """Test raqamlariga haqiqiy SMS yuborilmaydi (faqat DEBUG rejimida)."""
    if settings.DEBUG and phone in settings.OTP_TEST_PHONES:
        return {"provider": "test", "status": "skipped"}
    return get_sms_backend().send(phone, OTP_TEMPLATE.format(code=code))
