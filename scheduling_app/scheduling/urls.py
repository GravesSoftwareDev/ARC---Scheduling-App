from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('availability/', views.manage_availability, name='manage_availability'),
    path('operating-hours/', views.operating_hours, name='operating_hours'),
]
