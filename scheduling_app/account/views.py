from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Prefetch
from .forms import RegistrationForm, EditProfileForm
from .models import Employee, Department, Subject


_admin_check = lambda u: u.role == 'ADMIN'


@login_required
def edit_profile(request):
    if request.method == 'POST':
        form = EditProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('account:edit_profile')
    else:
        form = EditProfileForm(instance=request.user)
    return render(request, 'account/registration/edit_profile.html', {'form': form})


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
        .prefetch_related('departments', 'subjects')
        .order_by('last_name', 'first_name')
    )
    return render(request, 'account/employee_list.html', {'employees': employees})


@login_required
@user_passes_test(_admin_check)
def roster(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        emp_pk = request.POST.get('employee')
        dept_pk = request.POST.get('department')
        subj_code = request.POST.get('subject')

        emp = get_object_or_404(Employee, pk=emp_pk) if emp_pk else None

        if action == 'add_dept' and emp and dept_pk:
            dept = get_object_or_404(Department, pk=dept_pk)
            emp.departments.add(dept)
            messages.success(request, f"Added {emp.get_full_name()} to {dept.name}.")
        elif action == 'remove_dept' and emp and dept_pk:
            dept = get_object_or_404(Department, pk=dept_pk)
            emp.departments.remove(dept)
            messages.success(request, f"Removed {emp.get_full_name()} from {dept.name}.")
        elif action == 'add_subj' and emp and subj_code:
            subj = get_object_or_404(Subject, code=subj_code)
            emp.subjects.add(subj)
            messages.success(request, f"Added {emp.get_full_name()} to {subj.name}.")
        elif action == 'remove_subj' and emp and subj_code:
            subj = get_object_or_404(Subject, code=subj_code)
            emp.subjects.remove(subj)
            messages.success(request, f"Removed {emp.get_full_name()} from {subj.name}.")

        return redirect('account:roster')

    active_emps = Employee.objects.filter(is_active=True).order_by('last_name', 'first_name')

    departments = Department.objects.prefetch_related(
        Prefetch('employees', queryset=active_emps, to_attr='active_employees')
    ).order_by('name')

    subjects = Subject.objects.prefetch_related(
        Prefetch('employees', queryset=active_emps, to_attr='active_employees')
    ).order_by('name')

    all_employees = list(active_emps)

    return render(request, 'account/roster.html', {
        'departments': departments,
        'subjects': subjects,
        'all_employees': all_employees,
    })
