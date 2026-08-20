from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("csrf/", views.CSRFView.as_view(), name="csrf"),
    path("otp/request/", views.OTPRequestView.as_view(), name="otp-request"),
    path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
    path("google/", views.GoogleAuthView.as_view(), name="google"),
    path("refresh/", views.TokenRefreshCookieView.as_view(), name="refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/avatar/", views.MeAvatarView.as_view(), name="me-avatar"),
]
