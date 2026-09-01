from django.conf import settings
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("csrf/", views.CSRFView.as_view(), name="csrf"),
    path("google/", views.GoogleAuthView.as_view(), name="google"),
    path("methods/", views.AuthMethodsView.as_view(), name="methods"),
    path("refresh/", views.TokenRefreshCookieView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/avatar/", views.MeAvatarView.as_view(), name="me-avatar"),
]

if settings.AUTH_SMS_ENABLED:
    # SMS o'chirilganda bu manzillar umuman ro'yxatga olinmaydi — 404 qaytadi.
    # Shunda "endpoint bor, lekin ishlamaydi" degan chalkash holat bo'lmaydi.
    urlpatterns += [
        path("otp/request/", views.OTPRequestView.as_view(), name="otp-request"),
        path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
    ]
