from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("barber", "client", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("comment", "client__full_name", "barber__profile__full_name")
    autocomplete_fields = ("barber", "client")
    readonly_fields = ("booking", "created_at", "updated_at")
