from django.contrib import admin
from .models import WeeklyAvailability, OperatingHours


@admin.register(WeeklyAvailability)
class WeeklyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['user', 'day_of_week', 'start_time', 'end_time', 'availability_type']
    list_filter = ['availability_type', 'day_of_week']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'day_of_week']
    ordering = ['day_of_week', 'start_time']


@admin.register(OperatingHours)
class OperatingHoursAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'start_time', 'end_time']
    ordering = ['day_of_week']
