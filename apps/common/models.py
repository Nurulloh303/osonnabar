import uuid

from django.db import models


class UUIDModel(models.Model):
    """Barcha public jadvallar UUID primary key ishlatadi (TZ talabi)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("yaratilgan", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("yangilangan", auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True
