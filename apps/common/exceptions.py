"""Yagona xatolik formati — frontend har doim bir xil shaklni oladi.

    {
      "detail": "Bu vaqt allaqachon band",
      "code": "slot_taken",
      "errors": {"booking_time": ["Bu vaqt allaqachon band"]}
    }
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class SlotTakenError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Bu vaqt allaqachon band qilingan."
    default_code = "slot_taken"


class BusinessRuleError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Amalni bajarib bo'lmadi."
    default_code = "business_rule"


def _flatten_detail(detail) -> str:
    if isinstance(detail, dict):
        for value in detail.values():
            return _flatten_detail(value)
        return "Xatolik"
    if isinstance(detail, list):
        return _flatten_detail(detail[0]) if detail else "Xatolik"
    return str(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(detail=getattr(exc, "message_dict", None) or list(exc.messages))
    if isinstance(exc, IntegrityError) and "uniq_active_booking_slot" in str(exc):
        exc = SlotTakenError()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    code = getattr(exc, "default_code", None) or "error"
    if isinstance(exc, Http404):
        code = "not_found"

    payload = {"detail": _flatten_detail(detail), "code": code}
    if isinstance(detail, dict) and not (len(detail) == 1 and "detail" in detail):
        payload["errors"] = detail
    elif isinstance(detail, list):
        payload["errors"] = {"non_field_errors": detail}

    response.data = payload
    return response
