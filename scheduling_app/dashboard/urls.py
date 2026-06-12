from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('export.ics', views.export_schedule_ics, name='export_ics'),
]
