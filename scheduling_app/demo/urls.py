from django.urls import path
from . import views

app_name = 'demo'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('set-role/<str:role>/', views.set_role, name='set_role'),
]
