from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from .tokens import password_reset_token

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # path('login/',views.user_login,name='login'),
    path('login/', auth_views.LoginView.as_view(template_name='account/registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='account/registration/logout.html'), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='account/registration/password_change_form.html',
        success_url=reverse_lazy('dashboard:password_change_done'),
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='account/registration/password_change_done.html'), name='password_change_done'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='account/registration/password_reset_form.html',
        email_template_name='account/registration/password_reset_email.html',
        success_url=reverse_lazy('dashboard:password_reset_done'),
        token_generator=password_reset_token,
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='account/registration/password_reset_done.html'), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='account/registration/password_reset_confirm.html',
        success_url=reverse_lazy('dashboard:password_reset_complete'),
        token_generator=password_reset_token,
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(template_name='account/registration/password_reset_complete.html'), name='password_reset_complete'),
    path('registration/', views.registration, name='registration'),
    path('operating-hours/', views.operating_hours, name='operating_hours'),
    path('availability/', views.manage_availability, name='manage_availability'),
]