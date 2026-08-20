"""PostGIS'siz masofa hisoblash — Haversine formulasi SQL darajasida.

Yandex Maps'dan kelgan `lat`/`lng` bo'yicha "menga yaqin ustalar"ni saralash uchun.
"""

import math

from django.db.models import F, FloatField, Value
from django.db.models.functions import ACos, Cos, Least, Radians, Sin

EARTH_RADIUS_KM = 6371.0


def distance_expression(lat: float, lng: float, lat_field="location_lat", lng_field="location_lng"):
    """ORM annotate uchun km dagi masofa ifodasi."""
    return Value(EARTH_RADIUS_KM, output_field=FloatField()) * ACos(
        Least(
            Value(1.0, output_field=FloatField()),
            Cos(Radians(Value(lat, output_field=FloatField())))
            * Cos(Radians(F(lat_field)))
            * Cos(Radians(F(lng_field)) - Radians(Value(lng, output_field=FloatField())))
            + Sin(Radians(Value(lat, output_field=FloatField()))) * Sin(Radians(F(lat_field))),
        )
    )


def bounding_box(lat: float, lng: float, radius_km: float):
    """Indeksdan foydalanadigan tez dastlabki filtr (keyin aniq masofa hisoblanadi)."""
    lat_delta = radius_km / 110.574
    lng_delta = radius_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)
