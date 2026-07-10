from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee

@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    # `is_admin` and `availability_override_until` are intentionally left out
    # of these fieldsets — this is the app's own admin flag, not Django's
    # is_staff/is_superuser, and it has no edit UI here. The only ways to set
    # it are the app's own Employee List → Edit screen, or the Django shell
    # (see README.md "Bootstrapping the first admin user").
    fieldsets = UserAdmin.fieldsets + (
        ('Employee Details', {'fields': ('role', 'birthdate', 'part_time', 'desired_weekly_hours', 'wants_lunch_break')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'role', 'birthdate', 'part_time'),
        }),
    )
    list_display = ['id', 'username', 'first_name', 'last_name', 'role', 'birthdate', 'part_time']
    list_filter = ['role', 'part_time']
    search_fields = ['username', 'first_name', 'last_name', 'email']
