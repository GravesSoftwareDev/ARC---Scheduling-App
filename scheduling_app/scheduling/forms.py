from django import forms
from .models import OperatingHours, ScheduleEntry, DateOperatingHours


class OpenHoursForm(forms.ModelForm):
    class Meta:
        model = OperatingHours
        fields = ['start_time', 'end_time']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
        }


class ScheduleEntryForm(forms.ModelForm):
    class Meta:
        model = ScheduleEntry
        fields = ['user', 'department', 'date', 'start_time', 'end_time']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, scheduler=None, **kwargs):
        super().__init__(*args, **kwargs)
        from account.models import Employee, Department
        if scheduler and scheduler.role == 'SCHEDULER':
            # Restrict to employees/departments in the scheduler's departments
            dept_ids = scheduler.departments.values_list('id', flat=True)
            self.fields['user'].queryset = Employee.objects.filter(
                departments__in=dept_ids
            ).distinct().order_by('last_name', 'first_name')
            self.fields['department'].queryset = Department.objects.filter(
                id__in=dept_ids
            )
        else:
            self.fields['user'].queryset = Employee.objects.all().order_by('last_name', 'first_name')
            self.fields['department'].queryset = Department.objects.all()

        self.fields['user'].label_from_instance = lambda u: f"{u.last_name}, {u.first_name} ({u.username})"


class DateOperatingHoursForm(forms.ModelForm):
    class Meta:
        model = DateOperatingHours
        fields = ['date', 'is_closed', 'start_time', 'end_time', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Holiday, Special Event'}),
            'is_closed': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_is_closed'}),
        }
