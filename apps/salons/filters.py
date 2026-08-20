import django_filters as filters

from .models import Barber, Salon


class SalonFilter(filters.FilterSet):
    specialty = filters.CharFilter(field_name="specialty")
    city = filters.CharFilter(field_name="city", lookup_expr="iexact")
    district = filters.CharFilter(field_name="district", lookup_expr="iexact")
    min_rating = filters.NumberFilter(field_name="rating_avg", lookup_expr="gte")

    class Meta:
        model = Salon
        fields = ("specialty", "city", "district", "min_rating")


class BarberFilter(filters.FilterSet):
    specialty = filters.MultipleChoiceFilter(
        field_name="specialty",
        choices=Barber._meta.get_field("specialty").choices,
        help_text="men | women | kids | unisex (bir nechta bo'lishi mumkin)",
    )
    salon = filters.UUIDFilter(field_name="salon_id")
    city = filters.CharFilter(field_name="salon__city", lookup_expr="iexact")
    district = filters.CharFilter(field_name="salon__district", lookup_expr="iexact")
    min_rating = filters.NumberFilter(field_name="rating_avg", lookup_expr="gte")
    max_price = filters.NumberFilter(method="filter_max_price", help_text="Eng arzon xizmat narxi bo'yicha")

    class Meta:
        model = Barber
        fields = ("specialty", "salon", "city", "district", "min_rating")

    def filter_max_price(self, queryset, name, value):
        ids = [
            barber.id
            for barber in queryset.only("id", "services")
            if any(
                isinstance(s, dict) and s.get("price") is not None and s["price"] <= value
                for s in (barber.services or [])
            )
        ]
        return queryset.filter(id__in=ids)
