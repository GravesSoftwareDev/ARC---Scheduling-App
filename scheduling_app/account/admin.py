from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee, WeeklyAvailability, Subject, OperatingHours
# Register your models here.
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['name', 'code']
    ordering = ['name']

@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Employee Details', {'fields': ('role', 'department', 'subjects')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Employee Details', {'fields': ('role', 'department', 'subjects')}),
    )
    list_display = ['username', 'first_name', 'last_name', 'role', 'department', 'get_subjects']
    list_filter = ['role', 'department', 'subjects']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    
    def get_subjects(self, obj):
        return ', '.join([s.name for s in obj.subjects.all()]) or 'None'
    get_subjects.short_description = 'Subjects'

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