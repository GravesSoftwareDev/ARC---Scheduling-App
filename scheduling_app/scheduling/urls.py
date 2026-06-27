from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('availability/', views.manage_availability, name='manage_availability'),
    path('operating-hours/', views.operating_hours, name='operating_hours'),
    path('operating-hours/delete/<int:pk>/', views.delete_special_hours, name='delete_special_hours'),
    path('schedule/', views.schedule_builder, name='schedule_builder'),
    path('schedule/labels/<int:schedule_pk>/<int:emp_pk>/', views.employee_labels, name='employee_labels'),
    path('schedule/labels/<int:label_pk>/delete/', views.delete_employee_label, name='delete_employee_label'),
    path('export/teams/', views.export_teams_shifts, name='export_teams_shifts'),
]
