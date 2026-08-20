import django_filters as filters

from .models import Booking, BookingStatus


class BookingFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=BookingStatus.choices)
    date = filters.DateFilter(field_name="booking_date")
    date_from = filters.DateFilter(field_name="booking_date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="booking_date", lookup_expr="lte")
    barber = filters.UUIDFilter(field_name="barber_id")
    salon = filters.UUIDFilter(field_name="salon_id")
    scope = filters.CharFilter(method="filter_scope", help_text="`upcoming` | `past` | `today`")

    class Meta:
        model = Booking
        fields = ("status", "date", "date_from", "date_to", "barber", "salon")

    def filter_scope(self, queryset, name, value):
        from django.utils import timezone

        today = timezone.localdate()
        if value == "today":
            return queryset.filter(booking_date=today)
        if value == "upcoming":
            return queryset.filter(
                booking_date__gte=today, status__in=(BookingStatus.PENDING, BookingStatus.CONFIRMED)
            ).order_by("booking_date", "booking_time")
        if value == "past":
            return queryset.filter(booking_date__lt=today) | queryset.filter(
                status__in=(BookingStatus.COMPLETED, BookingStatus.CANCELLED)
            )
        return queryset
