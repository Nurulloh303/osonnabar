"""Web Push yuborish (VAPID).

Frontend TZ'sida `web-push` (Node.js) kutubxonasi ko'rsatilgan edi — bizning
backend Django bo'lgani uchun uning Python ekvivalenti `pywebpush` ishlatiladi.
Protokol bir xil (RFC 8291 + VAPID), shuning uchun frontend tomonida hech narsa
o'zgarmaydi: bir xil `applicationServerKey`, bir xil subscription obyekti.
"""

import json
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("apps.notifications")

#: Push xizmati shu kodlarni qaytarsa — obuna o'lgan, bazadan o'chiramiz.
DEAD_SUBSCRIPTION_CODES = (404, 410)


class PushNotConfigured(RuntimeError):
    """VAPID kalitlari sozlanmagan."""


def is_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_to_subscription(subscription, payload: dict) -> bool:
    """Bitta obunaga xabar yuboradi.

    `True` — yuborildi. `False` — obuna o'lik edi va o'chirildi.
    Boshqa xatoliklarda `WebPushException` ko'tariladi.
    """
    from pywebpush import WebPushException, webpush

    if not is_configured():
        raise PushNotConfigured("VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY sozlanmagan.")

    try:
        webpush(
            subscription_info=subscription.as_subscription_info,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # ⚠️ Har safar YANGI dict: pywebpush bu lug'atga `exp` va `aud` ni
            # yozib qo'yadi. Bitta dict'ni qayta ishlatsak, ikkinchi qurilmaga
            # birinchisining `aud` i bilan ketadi va push xizmati rad qiladi.
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            timeout=settings.PUSH_TIMEOUT_SECONDS,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in DEAD_SUBSCRIPTION_CODES:
            logger.info("Push obunasi o'lik (%s), o'chirildi: %s", status, subscription.endpoint[:60])
            subscription.delete()
            return False
        raise

    subscription.__class__.objects.filter(pk=subscription.pk).update(last_success_at=timezone.now())
    return True


def send_to_user(user_id, payload: dict) -> int:
    """Foydalanuvchining barcha qurilmalariga yuboradi. Yuborilganlar sonini qaytaradi."""
    from pywebpush import WebPushException

    from .models import PushSubscription

    if not is_configured():
        logger.debug("VAPID sozlanmagan — push o'tkazib yuborildi.")
        return 0

    sent = 0
    for subscription in PushSubscription.objects.filter(user_id=user_id):
        try:
            if send_to_subscription(subscription, payload):
                sent += 1
        except WebPushException as exc:
            # Bitta qurilma ishlamasa — qolganlariga yuborishda davom etamiz.
            logger.warning("Push yuborilmadi (%s): %s", subscription.endpoint[:60], exc)
        except Exception:  # noqa: BLE001
            logger.exception("Push yuborishda kutilmagan xatolik")
    return sent
