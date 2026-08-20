"""Rasm yuklashni tekshirish.

Ikki xavf yopiladi:

1. **Kengaytma orqali saqlangan XSS.** Fayl nomi foydalanuvchidan keladi.
   `rasm.html` deb yuborilsa, Pillow ichidagi baytlarni haqiqiy rasm deb tasdiqlaydi
   (GIF/HTML polyglot yasash qiyin emas), lekin fayl `/media/...html` bo'lib
   `text/html` sifatida beriladi va API domenida skript ishga tushadi.
   Yechim: fayl nomiga umuman ishonmaymiz — kengaytmani Pillow aniqlagan
   formatdan olamiz.

2. **Disk to'ldirish.** Hajm cheklovi.
"""

from django.conf import settings
from rest_framework import serializers

#: Pillow aniqlagan format → diskda ishlatiladigan kengaytma.
FORMAT_EXTENSIONS = {
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
    "GIF": "gif",
}

ALLOWED_EXTENSIONS = frozenset(FORMAT_EXTENSIONS.values()) | {"jpeg"}


def safe_extension(filename: str, fallback: str = "jpg") -> str:
    """Fayl nomidan faqat oq ro'yxatdagi kengaytmani oladi."""
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    return ext if ext in ALLOWED_EXTENSIONS else fallback


def validate_image_upload(value):
    """DRF `ImageField` uchun validator: hajm + haqiqiy format tekshiruvi."""
    max_size = settings.MAX_UPLOAD_SIZE
    if value.size > max_size:
        raise serializers.ValidationError(
            f"Rasm hajmi {max_size // (1024 * 1024)} MB dan oshmasligi kerak."
        )

    # DRF `ImageField` Pillow bilan ochib, `value.image` ni to'ldirib qo'yadi.
    image_format = getattr(getattr(value, "image", None), "format", None)
    if image_format is not None and image_format.upper() not in FORMAT_EXTENSIONS:
        allowed = ", ".join(sorted(FORMAT_EXTENSIONS))
        raise serializers.ValidationError(f"Faqat {allowed} formatdagi rasmlar qabul qilinadi.")

    return value


def upload_path(folder: str):
    """`upload_to` uchun: `<folder>/<obj.pk>.<xavfsiz kengaytma>`."""

    def build(instance, filename: str) -> str:
        return f"{folder}/{instance.pk}.{safe_extension(filename)}"

    return build
