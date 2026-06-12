from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .forms import RegistrationForm
from .models import Employee


_admin_check = lambda u: u.role == 'ADMIN'


@login_required
@user_passes_test(_admin_check)
def registration(request):
    if request.method == 'POST':
        user_form = RegistrationForm(request.POST)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.save()
            return render(
                request,
                'account/register_done.html',
                {'new_user': new_user}
            )
    else:
        user_form = RegistrationForm()
    return render(
        request,
        'account/register.html',
        {'user_form': user_form}
    )


@login_required
@user_passes_test(_admin_check)
def employee_list(request):
    if request.method == 'POST':
        emp_pk = request.POST.get('deactivate')
        if emp_pk:
            emp = get_object_or_404(Employee, pk=emp_pk)
            emp.is_active = False
            emp.save(update_fields=['is_active'])
            messages.success(request, f"{emp.get_full_name()} has been deactivated.")
        return redirect('account:employee_list')

    employees = (
        Employee.objects
        .filter(is_active=True)
        .order_by('last_name', 'first_name')
    )
    return render(request, 'account/employee_list.html', {'employees': employees})


@login_required
@user_passes_test(_admin_check)
def roster(request):
    from scheduling.models import Schedule

    if request.method == 'POST':
        action = request.POST.get('action')
        emp_pk = request.POST.get('employee')
        schedule_pk = request.POST.get('schedule')

        emp = get_object_or_404(Employee, pk=emp_pk) if emp_pk else None
        schedule = get_object_or_404(Schedule, pk=schedule_pk) if schedule_pk else None

        if action == 'add_member' and emp and schedule:
            schedule.members.add(emp)
            messages.success(request, f"Added {emp.get_full_name()} to {schedule.name}.")
        elif action == 'remove_member' and emp and schedule:
            schedule.members.remove(emp)
            messages.success(request, f"Removed {emp.get_full_name()} from {schedule.name}.")
        elif action == 'add_scheduler' and emp and schedule:
            schedule.schedulers.add(emp)
            messages.success(request, f"{emp.get_full_name()} can now schedule {schedule.name}.")
        elif action == 'remove_scheduler' and emp and schedule:
            schedule.schedulers.remove(emp)
            messages.success(request, f"Removed {emp.get_full_name()} as scheduler of {schedule.name}.")

        return redirect('account:roster')

    schedules = Schedule.objects.prefetch_related('members', 'schedulers').order_by('name')
    all_employees = list(Employee.objects.filter(is_active=True).order_by('last_name', 'first_name'))

    return render(request, 'account/roster.html', {
        'schedules': schedules,
        'all_employees': all_employees,
    })
