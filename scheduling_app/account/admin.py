from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee

@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Employee Details', {'fields': ('role', 'birthdate','part_time')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'role', 'birthdate','part_time'),
        }),
    )
    list_display = ['id', 'username', 'first_name', 'last_name', 'role', 'birthdate','part_time']
    list_filter = ['role','part_time']
    search_fields = ['username', 'first_name', 'last_name', 'email']
