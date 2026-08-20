import re

from rest_framework.exceptions import ValidationError

UZ_PHONE_RE = re.compile(r"^\+998(9[0-9]|3[3]|7[1]|8[8]|2[0]|6[1-9]|5[05]|7[0-9])\d{7}$")


def normalize_phone(raw: str) -> str:
    """`+998 90 123 45 67`, `998901234567`, `901234567` → `+998901234567`."""
    if not raw:
        raise ValidationError({"phone": ["Telefon raqam kiritilmadi."]})

    digits = re.sub(r"\D", "", str(raw))

    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 12 and digits.startswith("998"):
        pass
    elif len(digits) == 13 and digits.startswith("8998"):
        digits = digits[1:]
    else:
        raise ValidationError({"phone": ["Telefon raqam formati noto'g'ri. Namuna: +998901234567"]})

    phone = "+" + digits
    if not UZ_PHONE_RE.match(phone):
        raise ValidationError({"phone": ["Bunday operator kodi mavjud emas. Namuna: +998901234567"]})
    return phone
