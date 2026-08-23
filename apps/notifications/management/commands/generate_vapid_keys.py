"""Web Push uchun VAPID kalit juftligini yaratadi.

    python manage.py generate_vapid_keys

Natijani `.env` ga ko'chiring. Kalitlar bir marta yaratiladi va o'zgartirilmaydi:
almashtirilsa, mavjud barcha brauzer obunalari yaroqsiz bo'lib qoladi va
foydalanuvchilar qaytadan "Ruxsat berish" bosishlari kerak bo'ladi.
"""

import base64

from django.core.management.base import BaseCommand


def _b64(raw: bytes) -> str:
    """URL-safe base64, `=` to'ldiruvchilarsiz — Web Push standarti shuni kutadi."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class Command(BaseCommand):
    help = "VAPID public/private kalitlarini yaratadi (Web Push uchun)."

    def handle(self, *args, **options):
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid01

        vapid = Vapid01()
        vapid.generate_keys()

        private_key = _b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
        public_key = _b64(
            vapid.public_key.public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )

        self.stdout.write(self.style.SUCCESS("VAPID kalitlari yaratildi.\n"))
        self.stdout.write("Quyidagilarni `.env` ga qo'shing:\n")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public_key}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_key}")
        self.stdout.write("VAPID_SUBJECT=mailto:admin@qulaynavbat.uz\n")
        self.stdout.write(
            self.style.WARNING(
                "⚠️  PRIVATE kalitni hech kimga bermang va git'ga qo'shmang.\n"
                "⚠️  Frontend faqat PUBLIC kalitni ishlatadi "
                "(`GET /api/v1/notifications/vapid-key/` orqali ham olsa bo'ladi)."
            )
        )
