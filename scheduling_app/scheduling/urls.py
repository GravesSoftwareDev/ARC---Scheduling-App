from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('availability/', views.manage_availability, name='manage_availability'),
    path('operating-hours/', views.operating_hours, name='operating_hours'),
    path('operating-hours/delete/<int:pk>/', views.delete_special_hours, name='delete_special_hours'),
    path('schedule/', views.schedule_builder, name='schedule_builder'),
]
