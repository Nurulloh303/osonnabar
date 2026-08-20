"""Bo'sh vaqtlarni (slotlarni) hisoblash.

Manba: `BarberSchedule` (hafta kuni bo'yicha ish vaqti) − `BarberDayOff` (dam olish)
− faol bronlar (`pending` / `confirmed` / `completed`) − o'tib ketgan vaqtlar.
"""

from datetime import date as date_cls
from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.salons.models import Barber

from .models import ACTIVE_STATUSES, Booking


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _to_time(minutes: int) -> time:
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def busy_intervals(barber: Barber, on_date: date_cls) -> list[tuple[int, int]]:
    """Kun davomida band qilingan [boshlanish, tugash) oraliqlari (daqiqalarda)."""
    rows = Booking.objects.filter(
        barber=barber, booking_date=on_date, status__in=ACTIVE_STATUSES
    ).values_list("booking_time", "duration_minutes")
    return [(_to_minutes(t), _to_minutes(t) + (d or 30)) for t, d in rows]


def get_day_availability(barber: Barber, on_date: date_cls, service_duration: int | None = None) -> dict:
    """Bir kunlik slotlar ro'yxati (band bo'lganlari ham `is_available=false` bilan qaytadi).

    Front band vaqtlarni ham ko'rsatishi mumkin bo'lishi uchun to'liq ro'yxat beriladi.
    """
    weekday = on_date.weekday()
    schedule = barber.schedules.filter(weekday=weekday).first()
    is_day_off = barber.days_off.filter(date=on_date).exists()

    base = {
        "barber_id": barber.id,
        "date": on_date,
        "weekday": weekday,
        "is_working_day": False,
        "slot_minutes": schedule.slot_minutes if schedule else barber.default_slot_minutes,
        "slots": [],
    }

    if not barber.is_bookable or schedule is None or not schedule.is_working or is_day_off:
        return base

    step = schedule.slot_minutes
    duration = service_duration or step
    start = _to_minutes(schedule.start_time)
    end = _to_minutes(schedule.end_time)

    break_range = None
    if schedule.break_start and schedule.break_end:
        break_range = (_to_minutes(schedule.break_start), _to_minutes(schedule.break_end))

    busy = busy_intervals(barber, on_date)

    now = timezone.localtime()
    is_today = on_date == now.date()
    now_minutes = now.hour * 60 + now.minute

    slots = []
    cursor = start
    while cursor + duration <= end:
        slot_end = cursor + duration
        reason = None

        if is_today and cursor <= now_minutes:
            reason = "past"
        elif break_range and _overlaps(cursor, slot_end, *break_range):
            reason = "break"
        elif any(_overlaps(cursor, slot_end, b_start, b_end) for b_start, b_end in busy):
            reason = "booked"

        slots.append(
            {"time": _to_time(cursor).strftime("%H:%M"), "is_available": reason is None, "reason": reason}
        )
        cursor += step

    base["is_working_day"] = True
    base["slots"] = slots
    return base


def validate_slot(barber: Barber, on_date: date_cls, at_time: time, duration: int) -> None:
    """Bron yaratishdan oldingi qat'iy tekshiruv. Xato bo'lsa `ValidationError` ko'taradi."""
    from rest_framework.exceptions import ValidationError

    if not barber.is_bookable:
        raise ValidationError({"barber": ["Usta hozircha navbat qabul qilmayapti."]})

    if barber.days_off.filter(date=on_date).exists():
        raise ValidationError({"booking_date": ["Usta bu kuni dam oladi."]})

    schedule = barber.schedules.filter(weekday=on_date.weekday()).first()
    if schedule is None or not schedule.is_working:
        raise ValidationError({"booking_date": ["Usta bu hafta kuni ishlamaydi."]})

    start = _to_minutes(at_time)
    end = start + duration

    if start < _to_minutes(schedule.start_time) or end > _to_minutes(schedule.end_time):
        raise ValidationError(
            {
                "booking_time": [
                    f"Ish vaqti: {schedule.start_time:%H:%M}–{schedule.end_time:%H:%M}. "
                    "Tanlangan vaqt bu oraliqqa sig'maydi."
                ]
            }
        )

    # Slot setkasiga tushishi kerak (masalan 30 daqiqalik qadamda 14:17 qabul qilinmaydi)
    offset = start - _to_minutes(schedule.start_time)
    if offset % schedule.slot_minutes != 0:
        raise ValidationError(
            {"booking_time": [f"Vaqt {schedule.slot_minutes} daqiqalik qadamga mos kelishi kerak."]}
        )

    if schedule.break_start and schedule.break_end:
        if _overlaps(start, end, _to_minutes(schedule.break_start), _to_minutes(schedule.break_end)):
            raise ValidationError({"booking_time": ["Bu vaqt tanaffusga to'g'ri keladi."]})

    starts_at = timezone.make_aware(
        datetime.combine(on_date, at_time), timezone.get_current_timezone()
    )
    if starts_at <= timezone.now():
        raise ValidationError({"booking_time": ["O'tib ketgan vaqtga navbat olib bo'lmaydi."]})


def has_conflict(barber_id, on_date: date_cls, at_time: time, duration: int, exclude_id=None) -> bool:
    """Vaqt oralig'ida boshqa faol bron bormi (davomiylikni hisobga olib)."""
    qs = Booking.objects.filter(barber_id=barber_id, booking_date=on_date, status__in=ACTIVE_STATUSES)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    start = _to_minutes(at_time)
    end = start + duration
    for t, d in qs.values_list("booking_time", "duration_minutes"):
        b_start = _to_minutes(t)
        if _overlaps(start, end, b_start, b_start + (d or 30)):
            return True
    return False


def next_available_slot(barber: Barber, days_ahead: int = 14) -> dict | None:
    """Ro'yxatda "Eng yaqin bo'sh vaqt" ko'rsatish uchun."""
    today = timezone.localdate()
    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        data = get_day_availability(barber, day)
        for slot in data["slots"]:
            if slot["is_available"]:
                return {"date": day.isoformat(), "time": slot["time"]}
    return None
