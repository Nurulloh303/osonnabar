from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PhoneOTP, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = ("phone", "full_name", "role", "is_active", "is_phone_verified", "created_at")
    list_filter = ("role", "is_active", "is_phone_verified")
    search_fields = ("phone", "full_name", "email")
    readonly_fields = ("created_at", "updated_at", "last_login")

    fieldsets = (
        (None, {"fields": ("phone", "email", "password")}),
        ("Profil", {"fields": ("full_name", "avatar", "role")}),
        ("Holat", {"fields": ("is_active", "is_phone_verified", "is_staff", "is_superuser")}),
        ("Google", {"fields": ("google_sub",), "classes": ("collapse",)}),
        ("Sanalar", {"fields": ("created_at", "updated_at", "last_login")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "full_name", "role", "password1", "password2")}),
    )


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ("phone", "purpose", "attempts", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("phone",)
    readonly_fields = ("code_hash",)
