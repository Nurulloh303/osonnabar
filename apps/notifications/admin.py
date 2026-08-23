from django.contrib import admin

from .models import Notification, PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "short_endpoint", "user_agent", "created_at", "last_success_at")
    search_fields = ("user__phone", "user__full_name", "endpoint")
    readonly_fields = ("endpoint", "auth_keys", "created_at", "last_success_at")

    @admin.display(description="endpoint")
    def short_endpoint(self, obj) -> str:
        return f"{obj.endpoint[:50]}…"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "kind", "is_read", "push_sent_at", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("user__phone", "user__full_name", "title", "body")
    readonly_fields = ("created_at", "push_sent_at")
