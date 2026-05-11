from django.shortcuts import render, redirect
from django.contrib.auth import login
from account.models import Employee


_DEMO_USERNAMES = {
    'employee': 'demo_employee',
    'scheduler': 'demo_scheduler',
    'admin': 'demo_admin',
}

_ROLE_REDIRECT = {
    'employee': 'dashboard:dashboard',
    'scheduler': 'scheduling:schedule_builder',
    'admin': 'account:employee_list',
}


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')
    return render(request, 'demo/landing.html')


def set_role(request, role):
    username = _DEMO_USERNAMES.get(role)
    if not username:
        return redirect('demo:landing')
    try:
        user = Employee.objects.get(username=username)
    except Employee.DoesNotExist:
        return redirect('demo:landing')
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    return redirect(_ROLE_REDIRECT.get(role, 'dashboard:dashboard'))
