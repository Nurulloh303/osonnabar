from django.contrib import admin

from .models import Barber, BarberDayOff, BarberSchedule, Salon


class BarberScheduleInline(admin.TabularInline):
    model = BarberSchedule
    extra = 0


class BarberInline(admin.TabularInline):
    model = Barber
    extra = 0
    fields = ("profile", "specialty", "status", "rating_avg")
    readonly_fields = ("rating_avg",)
    show_change_link = True


@admin.register(Salon)
class SalonAdmin(admin.ModelAdmin):
    list_display = ("name", "specialty", "district", "city", "rating_avg", "reviews_count", "is_active")
    list_filter = ("specialty", "city", "district", "is_active")
    search_fields = ("name", "address", "district")
    readonly_fields = ("rating_avg", "reviews_count", "created_at", "updated_at")
    inlines = [BarberInline]


@admin.register(Barber)
class BarberAdmin(admin.ModelAdmin):
    list_display = ("__str__", "salon", "specialty", "status", "rating_avg", "completed_bookings")
    list_filter = ("status", "specialty", "salon")
    search_fields = ("profile__full_name", "profile__phone", "salon__name")
    autocomplete_fields = ("profile", "salon")
    readonly_fields = ("rating_avg", "reviews_count", "completed_bookings", "created_at", "updated_at")
    inlines = [BarberScheduleInline]
    actions = ("block_barbers", "activate_barbers")

    @admin.action(description="Tanlanganlarni bloklash")
    def block_barbers(self, request, queryset):
        queryset.update(status=Barber.Status.BLOCKED)

    @admin.action(description="Tanlanganlarni faollashtirish")
    def activate_barbers(self, request, queryset):
        queryset.update(status=Barber.Status.ACTIVE)


@admin.register(BarberDayOff)
class BarberDayOffAdmin(admin.ModelAdmin):
    list_display = ("barber", "date", "reason")
    list_filter = ("date",)
