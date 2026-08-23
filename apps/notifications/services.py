"""Xabarnoma yaratish va yuborish.

Ikki bosqich ataylab ajratilgan:

1. **Bazaga yozish** — sinxron va ishonchli. Sayt ichidagi qo'ng'iroqcha shunga
   tayanadi, shuning uchun push ishlamasa ham xabar yo'qolmaydi.
2. **Push yuborish** — "iloji boricha" (best-effort), tranzaksiya yopilgandan
   keyin alohida oqimda. Push xizmati (FCM va h.k.) sekin javob berishi mumkin;
   uni so'rov ichida kutsak, usta "Tasdiqlash" tugmasini bosganda API javobi
   bir necha soniyaga cho'zilardi va gunicorn worker'i band bo'lib turardi.
"""

import logging
import threading

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from .models import Notification, NotificationKind

logger = logging.getLogger("apps.notifications")


def _deliver(notification_id, payload: dict) -> None:
    """Alohida oqimda ishlaydi — bu yerdagi xatolik so'rovga ta'sir qilmaydi."""
    from . import push

    try:
        notification = Notification.objects.filter(pk=notification_id).first()
        if notification is None:
            return
        if push.send_to_user(notification.user_id, payload):
            Notification.objects.filter(pk=notification_id).update(push_sent_at=timezone.now())
    except Exception:  # noqa: BLE001
        logger.exception("Push yetkazishda xatolik (notification=%s)", notification_id)
    finally:
        # Oqim o'z DB ulanishini ochadi — uni yopmasak, ulanishlar to'planib qoladi.
        connections.close_all()


def _dispatch(notification_id, payload: dict) -> None:
    if not settings.PUSH_ENABLED:
        return
    if settings.PUSH_SEND_ASYNC:
        threading.Thread(
            target=_deliver, args=(notification_id, payload), daemon=True, name="web-push"
        ).start()
    else:
        _deliver(notification_id, payload)


def notify(
    user,
    *,
    title: str,
    body: str,
    kind: str = NotificationKind.SYSTEM,
    url: str = "",
    booking=None,
    send_push: bool = True,
) -> Notification:
    """Xabarnoma yaratadi va (kerak bo'lsa) push yuboradi."""
    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        kind=kind,
        url=url,
        booking=booking,
    )

    if send_push:
        payload = {
            "id": str(notification.id),
            "title": title,
            "body": body,
            "kind": kind,
            "url": url or settings.FRONTEND_URL,
        }
        # Tranzaksiya muvaffaqiyatli yopilgandan keyingina yuboramiz: aks holda
        # bron bekor qilish rollback bo'lsa ham mijozga "bekor qilindi" push ketardi.
        transaction.on_commit(lambda: _dispatch(notification.id, payload))

    return notification


# ── Bron hodisalari uchun tayyor matnlar ─────────────────────────────────────
def _barber_name(booking) -> str:
    return booking.barber.profile.display_name or "Usta"


def _when(booking) -> str:
    return f"{booking.booking_date:%d.%m.%Y} {booking.booking_time:%H:%M}"


def booking_confirmed(booking) -> Notification:
    return notify(
        booking.client,
        title="Navbatingiz tasdiqlandi",
        body=f"{_barber_name(booking)} · {_when(booking)} · {booking.service_name}",
        kind=NotificationKind.BOOKING_CONFIRMED,
        url=f"/bookings/{booking.id}",
        booking=booking,
    )


def booking_cancelled(booking, *, cancelled_by=None) -> Notification | None:
    """Bekor qilgan odamning o'ziga xabar bermaymiz — u allaqachon biladi."""
    by_barber = cancelled_by is not None and cancelled_by.id != booking.client_id
    if not by_barber:
        return None

    reason = f" Sabab: {booking.cancel_reason}" if booking.cancel_reason else ""
    return notify(
        booking.client,
        title="Navbatingiz bekor qilindi",
        body=f"{_barber_name(booking)} · {_when(booking)}.{reason}",
        kind=NotificationKind.BOOKING_CANCELLED,
        url=f"/bookings/{booking.id}",
        booking=booking,
    )


def booking_completed(booking) -> Notification:
    return notify(
        booking.client,
        title="Xizmat yakunlandi",
        body=f"{_barber_name(booking)} xizmatini yakunladi. Sharh qoldirishni unutmang!",
        kind=NotificationKind.BOOKING_COMPLETED,
        url=f"/bookings/{booking.id}",
        booking=booking,
    )


def booking_created_for_barber(booking) -> Notification:
    """Ustaga yangi navbat tushgani haqida."""
    return notify(
        booking.barber.profile,
        title="Yangi navbat",
        body=f"{booking.client.display_name} · {_when(booking)} · {booking.service_name}",
        kind=NotificationKind.BOOKING_CREATED,
        url=f"/barber/bookings/{booking.id}",
        booking=booking,
    )


def booking_reminder(booking, minutes_left: int) -> Notification:
    return notify(
        booking.client,
        title="Navbatingiz yaqinlashdi",
        body=(
            f"{minutes_left} daqiqadan so'ng: {_barber_name(booking)} · "
            f"{booking.booking_time:%H:%M} · {booking.service_name}"
        ),
        kind=NotificationKind.BOOKING_REMINDER,
        url=f"/bookings/{booking.id}",
        booking=booking,
    )
