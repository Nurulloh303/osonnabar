"""Agregatsiya so'rovlari — usta va super admin panellari uchun.

Barchasi bitta-ikkita SQL so'rovga siqilgan (`aggregate` + `filter=Q(...)`),
shuning uchun ma'lumot ko'paysa ham panel tez ochiladi.
"""

from datetime import date, timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus

REVENUE_STATUS = BookingStatus.COMPLETED  # daromad faqat yakunlangan xizmatdan hisoblanadi


def _period_start(period: str, today: date) -> date | None:
    return {
        "day": today,
        "week": today - timedelta(days=today.weekday()),
        "month": today.replace(day=1),
        "year": today.replace(month=1, day=1),
        "all": None,
    }.get(period, today.replace(day=1))


def booking_stats(queryset) -> dict:
    """Berilgan bronlar to'plami bo'yicha umumiy ko'rsatkichlar."""
    today = timezone.localdate()
    month_start = today.replace(day=1)

    return queryset.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=BookingStatus.PENDING)),
        confirmed=Count("id", filter=Q(status=BookingStatus.CONFIRMED)),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        cancelled=Count("id", filter=Q(status=BookingStatus.CANCELLED)),
        today_total=Count("id", filter=Q(booking_date=today)),
        revenue_total=Sum("price", filter=Q(status=REVENUE_STATUS), default=0),
        revenue_today=Sum("price", filter=Q(status=REVENUE_STATUS, booking_date=today), default=0),
        revenue_month=Sum(
            "price", filter=Q(status=REVENUE_STATUS, booking_date__gte=month_start), default=0
        ),
        avg_check=Avg("price", filter=Q(status=REVENUE_STATUS)),
    )


def revenue_timeseries(queryset, days: int = 30) -> list[dict]:
    """Oxirgi `days` kun uchun kunlik daromad — panel grafigi uchun."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    # `booking_date` allaqachon DateField — uni TruncDate bilan o'rash SQLite'da
    # xatoga olib keladi, Postgres'da esa kunni vaqt mintaqasiga qarab surib yuboradi.
    rows = (
        queryset.filter(status=REVENUE_STATUS, booking_date__gte=start)
        .values("booking_date")
        .annotate(revenue=Sum("price"), bookings=Count("id"))
        .order_by("booking_date")
    )
    by_day = {row["booking_date"]: row for row in rows}

    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = by_day.get(day)
        result.append(
            {
                "date": day.isoformat(),
                "revenue": int(row["revenue"]) if row else 0,
                "bookings": row["bookings"] if row else 0,
            }
        )
    return result


def barber_dashboard(barber, period: str = "month") -> dict:
    today = timezone.localdate()
    qs = Booking.objects.filter(barber=barber)

    start = _period_start(period, today)
    period_qs = qs.filter(booking_date__gte=start) if start else qs

    stats = booking_stats(qs)
    period_stats = period_qs.aggregate(
        bookings=Count("id"),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        revenue=Sum("price", filter=Q(status=REVENUE_STATUS), default=0),
        unique_clients=Count("client", distinct=True, filter=Q(status=REVENUE_STATUS)),
    )

    top_services = list(
        qs.filter(status=REVENUE_STATUS)
        .values("service_name")
        .annotate(count=Count("id"), revenue=Sum("price"))
        .order_by("-count")[:5]
    )

    return {
        "period": period,
        "period_from": start.isoformat() if start else None,
        "totals": stats,
        "period_totals": period_stats,
        "rating": {"average": barber.rating_avg, "reviews": barber.reviews_count},
        "chart": revenue_timeseries(qs, days=30),
        "top_services": top_services,
    }


def superadmin_dashboard(period: str = "month") -> dict:
    from django.contrib.auth import get_user_model

    from apps.salons.models import Barber, Salon

    User = get_user_model()
    today = timezone.localdate()
    start = _period_start(period, today)

    qs = Booking.objects.all()
    period_qs = qs.filter(booking_date__gte=start) if start else qs

    users = User.objects.aggregate(
        clients=Count("id", filter=Q(role=User.Role.CLIENT)),
        barbers=Count("id", filter=Q(role=User.Role.BARBER)),
        blocked=Count("id", filter=Q(is_active=False)),
        new_this_month=Count("id", filter=Q(created_at__date__gte=today.replace(day=1))),
    )
    barbers = Barber.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Barber.Status.ACTIVE)),
        blocked=Count("id", filter=Q(status=Barber.Status.BLOCKED)),
    )

    top_barbers = list(
        Barber.objects.filter(bookings__status=REVENUE_STATUS)
        .annotate(revenue=Sum("bookings__price"), orders=Count("bookings"))
        .order_by("-revenue")
        .values(
            "id", "profile__full_name", "salon__name", "revenue", "orders", "rating_avg"
        )[:10]
    )

    return {
        "period": period,
        "period_from": start.isoformat() if start else None,
        "users": users,
        "barbers": barbers,
        "salons": Salon.objects.aggregate(
            total=Count("id"), active=Count("id", filter=Q(is_active=True))
        ),
        "bookings": booking_stats(qs),
        "period_totals": period_qs.aggregate(
            bookings=Count("id"),
            revenue=Sum("price", filter=Q(status=REVENUE_STATUS), default=0),
        ),
        "chart": revenue_timeseries(qs, days=30),
        "top_barbers": top_barbers,
    }
