from django.contrib import admin

from .models import Booking, BookingStatus


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_date",
        "booking_time",
        "barber",
        "client",
        "service_name",
        "price",
        "status",
    )
    list_filter = ("status", "booking_date", "barber__salon")
    search_fields = ("client__full_name", "client__phone", "barber__profile__full_name", "service_name")
    autocomplete_fields = ("client", "barber")
    date_hierarchy = "booking_date"
    readonly_fields = ("created_at", "updated_at", "confirmed_at", "completed_at", "cancelled_at")
    actions = ("mark_confirmed", "mark_completed")

    @admin.action(description="Tasdiqlash")
    def mark_confirmed(self, request, queryset):
        queryset.filter(status=BookingStatus.PENDING).update(status=BookingStatus.CONFIRMED)

    @admin.action(description="Yakunlash")
    def mark_completed(self, request, queryset):
        queryset.exclude(status=BookingStatus.CANCELLED).update(status=BookingStatus.COMPLETED)
