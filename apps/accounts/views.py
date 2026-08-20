import logging

from django.conf import settings
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import clear_auth_cookies, issue_tokens, set_auth_cookies
from .google import verify_google_id_token
from .models import OTPPurpose, PhoneOTP, User
from .serializers import (
    AuthResponseSerializer,
    AvatarUploadSerializer,
    GoogleAuthSerializer,
    MessageSerializer,
    OTPRequestResponseSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    UserSerializer,
)
from .sms import SMSError, send_otp_sms

logger = logging.getLogger("apps.accounts")


def _auth_response(request, user, *, is_new_user: bool, status_code=status.HTTP_200_OK):
    """Cookie'larni o'rnatib, foydalanuvchi ma'lumotini qaytaradi."""
    access, refresh = issue_tokens(user)
    payload = {"user": UserSerializer(user, context={"request": request}).data, "is_new_user": is_new_user}

    # Mobil ilova / Swagger uchun tokenlarni javobda ham olish imkoniyati
    if request.query_params.get("with_tokens") in ("1", "true", "yes"):
        payload["access"] = access
        payload["refresh"] = refresh

    response = Response(payload, status=status_code)
    return set_auth_cookies(response, access, refresh)


@extend_schema(tags=["auth"])
class CSRFView(APIView):
    """Frontend ilova yuklanishida bir marta chaqiradi va `csrftoken` cookie'sini oladi.

    Keyingi POST/PATCH/DELETE so'rovlarda shu qiymatni `X-CSRFToken` header'iga qo'yish kerak.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses=MessageSerializer, summary="CSRF token olish")
    def get(self, request):
        token = get_token(request)
        return Response({"detail": "ok", "csrftoken": token})


@extend_schema(tags=["auth"])
class OTPRequestView(APIView):
    """Telefon raqamga 4 xonali tasdiqlash kodini yuboradi."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "otp_request"

    @extend_schema(
        request=OTPRequestSerializer,
        responses={200: OTPRequestResponseSerializer},
        summary="SMS kod so'rash",
    )
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        # Spam himoyasi: oxirgi kod yuborilganidan beri cooldown o'tganmi?
        last = PhoneOTP.objects.filter(phone=phone, purpose=OTPPurpose.LOGIN).first()
        if last:
            elapsed = (timezone.now() - last.created_at).total_seconds()
            cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
            if elapsed < cooldown:
                return Response(
                    {
                        "detail": f"Yangi kod {int(cooldown - elapsed)} soniyadan so'ng yuboriladi.",
                        "code": "resend_cooldown",
                        "resend_after": int(cooldown - elapsed),
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        otp, code = PhoneOTP.issue(phone)

        try:
            send_otp_sms(phone, code)
        except SMSError as exc:
            logger.error("SMS yuborilmadi (%s): %s", phone, exc)
            otp.delete()
            return Response(
                {"detail": "SMS yuborishda xatolik. Birozdan so'ng qayta urinib ko'ring.", "code": "sms_failed"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        data = {
            "phone": phone,
            "expires_in": settings.OTP_TTL_SECONDS,
            "resend_after": settings.OTP_RESEND_COOLDOWN_SECONDS,
            "is_new_user": not User.objects.filter(phone=phone).exists(),
        }
        if settings.DEBUG and settings.OTP_RETURN_IN_RESPONSE:
            data["code"] = code
        return Response(data)


@extend_schema(tags=["auth"])
class OTPVerifyView(APIView):
    """Kodni tekshiradi. Foydalanuvchi bo'lmasa — avtomatik yaratadi (mijoz roli bilan)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "otp_verify"

    @extend_schema(
        request=OTPVerifySerializer,
        responses={200: AuthResponseSerializer},
        parameters=[OpenApiParameter("with_tokens", bool, description="Tokenlarni javobda ham qaytarish")],
        summary="SMS kodni tasdiqlash va tizimga kirish",
    )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        full_name = serializer.validated_data.get("full_name", "").strip()

        otp = (
            PhoneOTP.objects.filter(phone=phone, purpose=OTPPurpose.LOGIN, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            return Response(
                {"detail": "Kod topilmadi. Iltimos, qaytadan so'rang.", "code": "otp_not_found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp.is_expired:
            return Response(
                {"detail": "Kod muddati tugagan. Yangi kod so'rang.", "code": "otp_expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            otp.mark_used()
            return Response(
                {"detail": "Urinishlar soni tugadi. Yangi kod so'rang.", "code": "otp_attempts_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not otp.check_code(code):
            PhoneOTP.objects.filter(pk=otp.pk).update(attempts=otp.attempts + 1)
            left = settings.OTP_MAX_ATTEMPTS - (otp.attempts + 1)
            return Response(
                {"detail": f"Kod noto'g'ri. Qolgan urinishlar: {left}", "code": "otp_invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp.mark_used()

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={"full_name": full_name, "role": User.Role.CLIENT, "is_phone_verified": True},
            )
            updates = []
            if not user.is_phone_verified:
                user.is_phone_verified = True
                updates.append("is_phone_verified")
            if full_name and not user.full_name:
                user.full_name = full_name
                updates.append("full_name")
            if updates:
                user.save(update_fields=updates)

        if not user.is_active:
            return Response(
                {"detail": "Akkauntingiz bloklangan. Administratorga murojaat qiling.", "code": "account_blocked"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _auth_response(request, user, is_new_user=created)


@extend_schema(tags=["auth"])
class GoogleAuthView(APIView):
    """Google Sign-In `id_token`ini tekshirib, sessiya ochadi."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={200: AuthResponseSerializer},
        summary="Google orqali kirish",
    )
    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        info = verify_google_id_token(serializer.validated_data["id_token"])

        created = False
        with transaction.atomic():
            user = User.objects.filter(google_sub=info["sub"]).first()
            if user is None and info["email"]:
                user = User.objects.filter(email__iexact=info["email"]).first()
                if user is not None:
                    user.google_sub = info["sub"]
                    user.save(update_fields=["google_sub"])
            if user is None:
                user = User.objects.create_user(
                    email=info["email"],
                    full_name=info["full_name"],
                    google_sub=info["sub"],
                    role=User.Role.CLIENT,
                )
                created = True

        if not user.is_active:
            return Response(
                {"detail": "Akkauntingiz bloklangan.", "code": "account_blocked"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return _auth_response(request, user, is_new_user=created)


@extend_schema(tags=["auth"])
class TokenRefreshCookieView(APIView):
    """`on_refresh` cookie'si asosida yangi access token beradi (rotatsiya bilan)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(responses={200: MessageSerializer}, summary="Tokenni yangilash")
    def post(self, request):
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH) or request.data.get("refresh")
        if not raw:
            return Response(
                {"detail": "Refresh token topilmadi.", "code": "no_refresh_token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            refresh = RefreshToken(raw)
            user = User.objects.get(pk=refresh["user_id"], is_active=True)
        except (TokenError, User.DoesNotExist, KeyError):
            response = Response(
                {"detail": "Sessiya muddati tugagan. Qaytadan kiring.", "code": "token_invalid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            return clear_auth_cookies(response)

        access, new_refresh = issue_tokens(user)
        payload = {"detail": "ok"}
        if request.query_params.get("with_tokens") in ("1", "true", "yes"):
            payload |= {"access": access, "refresh": new_refresh}
        return set_auth_cookies(Response(payload), access, new_refresh)


@extend_schema(tags=["auth"])
class LogoutView(APIView):
    """Cookie'larni o'chiradi."""

    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={200: MessageSerializer}, summary="Chiqish")
    def post(self, request):
        return clear_auth_cookies(Response({"detail": "Tizimdan chiqdingiz."}))


@extend_schema(tags=["auth"])
class MeView(RetrieveUpdateAPIView):
    """Joriy foydalanuvchi profili (o'qish / `full_name` yangilash)."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "put", "head", "options"]

    def get_object(self):
        return User.objects.select_related("barber").get(pk=self.request.user.pk)


@extend_schema(tags=["auth"])
class MeAvatarView(APIView):
    """Profil rasmini yuklash (multipart/form-data)."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(request=AvatarUploadSerializer, responses={200: UserSerializer}, summary="Avatar yuklash")
    def post(self, request):
        serializer = AvatarUploadSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(responses={204: None}, summary="Avatarni o'chirish")
    def delete(self, request):
        if request.user.avatar:
            request.user.avatar.delete(save=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
