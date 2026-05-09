from django.contrib import admin
from .models import WeeklyAvailability, OperatingHours, WeeklySchedule, ScheduleEntry, DateOperatingHours, Subject


@admin.register(WeeklyAvailability)
class WeeklyAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['user', 'day_of_week', 'start_time', 'end_time', 'availability_type']
    list_filter = ['availability_type', 'day_of_week']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']


@admin.register(OperatingHours)
class OperatingHoursAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'start_time', 'end_time']
    ordering = ['day_of_week']


@admin.register(WeeklySchedule)
class WeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = ['user', 'day_of_week', 'start_time', 'end_time', 'department']
    ordering = ['day_of_week', 'start_time']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'locations', 'account_subject_code']
    list_filter = ['department']
    search_fields = ['name']
    ordering = ['department__name', 'name']


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'subject', 'date', 'start_time', 'end_time', 'created_by']
    list_filter = ['department', 'subject', 'date']
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    ordering = ['date', 'start_time']
    date_hierarchy = 'date'


@admin.register(DateOperatingHours)
class DateOperatingHoursAdmin(admin.ModelAdmin):
    list_display = ['date', 'is_closed', 'start_time', 'end_time', 'note']
    ordering = ['date']
    list_filter = ['is_closed']
