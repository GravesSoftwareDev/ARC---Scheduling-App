from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Case, IntegerField, Value, When
from .forms import RegistrationForm, EditEmployeeForm
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
            name = emp.get_full_name()
            emp.delete()
            messages.success(request, f"{name} has been removed.")
        return redirect('account:employee_list')

    employees = (
        Employee.objects
        .filter(is_active=True)
        .order_by('last_name', 'first_name')
    )
    return render(request, 'account/employee_list.html', {'employees': employees})


@login_required
@user_passes_test(lambda u: u.username == 'gravess')
def reset_all_availability(request):
    if request.method != 'POST':
        return redirect('account:employee_list')
    from scheduling.models import WeeklyAvailability, OperatingHours
    operating_hours = list(OperatingHours.objects.all())
    if not operating_hours:
        messages.warning(request, "No operating hours configured.")
        return redirect('account:employee_list')
    employees = Employee.objects.filter(is_active=True)
    WeeklyAvailability.objects.filter(user__in=employees).delete()
    new_blocks = [
        WeeklyAvailability(
            user=emp,
            day_of_week=oh.day_of_week,
            start_time=oh.start_time,
            end_time=oh.end_time,
            availability_type=WeeklyAvailability.AvailabilityType.AVAILABLE,
        )
        for emp in employees
        for oh in operating_hours
    ]
    WeeklyAvailability.objects.bulk_create(new_blocks)
    messages.success(request, f"Availability reset to full operating hours for {employees.count()} employees.")
    return redirect('account:employee_list')


@login_required
@user_passes_test(_admin_check)
def edit_employee(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EditEmployeeForm(request.POST, instance=emp)
        if form.is_valid():
            form.save()
            messages.success(request, f"{emp.get_full_name()} updated.")
            return redirect('account:employee_list')
    else:
        form = EditEmployeeForm(instance=emp)
    return render(request, 'account/edit_employee.html', {'form': form, 'emp': emp})


@login_required
@user_passes_test(_admin_check)
def roster(request):
    from scheduling.models import Schedule
    from scheduling.forms import ScheduleForm

    if request.method == 'POST':
        action = request.POST.get('action')
        emp_pk = request.POST.get('employee')
        schedule_pk = request.POST.get('schedule')

        emp = get_object_or_404(Employee, pk=emp_pk) if emp_pk else None
        schedule = get_object_or_404(Schedule, pk=schedule_pk) if schedule_pk else None

        if action == 'create_schedule':
            form = ScheduleForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, f"Schedule '{form.cleaned_data['name']}' created.")
        elif action == 'edit_schedule' and schedule:
            form = ScheduleForm(request.POST, instance=schedule)
            if form.is_valid():
                form.save()
                messages.success(request, f"Schedule renamed to '{form.cleaned_data['name']}'.")
        elif action == 'delete_schedule' and schedule:
            from scheduling.models import ScheduleEntry, WeeklySchedule
            name = schedule.name
            ScheduleEntry.objects.filter(schedule=schedule).delete()
            WeeklySchedule.objects.filter(schedule=schedule).delete()
            schedule.delete()
            messages.success(request, f"Schedule '{name}' and all its entries deleted.")
        elif action == 'add_member' and emp and schedule:
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

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect('account:roster')

    schedules = Schedule.objects.prefetch_related('members', 'schedulers').order_by('name')
    all_employees = list(
        Employee.objects.filter(is_active=True).annotate(
            role_order=Case(
                When(role='ADMIN', then=Value(0)),
                When(role='ARC_ASSISTANT', then=Value(1)),
                When(role='TUTOR', then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by('role_order', 'first_name')
    )

    return render(request, 'account/roster.html', {
        'schedules': schedules,
        'all_employees': all_employees,
        'schedule_form': ScheduleForm(),
    })
