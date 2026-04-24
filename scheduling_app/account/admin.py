from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee, Subject, Department

# Register your models here.
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['name', 'code']
    ordering = ['name']

@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Employee Details', {'fields': ('role', 'birthdate', 'departments', 'subjects')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'role', 'birthdate', 'departments', 'subjects'),
        }),
    )
    list_display = ['id','username', 'first_name', 'last_name', 'role', 'birthdate', 'get_departments', 'get_subjects']
    list_filter = ['role', 'departments', 'subjects']
    search_fields = ['username', 'first_name', 'last_name', 'email']

    def get_departments(self, obj):
        return ', '.join([d.name for d in obj.departments.all()]) or 'None'
    get_departments.short_description = 'Departments'

    def get_subjects(self, obj):
        return ', '.join([s.name for s in obj.subjects.all()]) or 'None'
    get_subjects.short_description = 'Subjects'

