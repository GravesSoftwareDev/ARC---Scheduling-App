from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee, Subject
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

