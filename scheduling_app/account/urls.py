from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'account'

urlpatterns = [
    # path('login/',views.user_login,name='login'),
    path('login/', auth_views.LoginView.as_view(template_name='account/registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='account/registration/logout.html'), name='logout'),
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='account/registration/password_change_form.html',
        success_url=reverse_lazy('account:password_change_done'),
    ), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='account/registration/password_change_done.html'), name='password_change_done'),
    path('registration/', views.registration, name='registration'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<int:pk>/edit/', views.edit_employee, name='edit_employee'),
    path('employees/<int:pk>/reset-password/', views.reset_employee_password, name='reset_employee_password'),
    path('employees/reset-availability/', views.reset_all_availability, name='reset_all_availability'),
    path('roster/', views.roster, name='roster'),
]