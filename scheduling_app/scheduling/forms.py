from django import forms
from .models import OperatingHours, ScheduleEntry, DateOperatingHours, Schedule


class EmployeePreferencesForm(forms.ModelForm):
    class Meta:
        from account.models import Employee
        model = Employee
        fields = ['desired_weekly_hours', 'wants_lunch_break']
        widgets = {
            'desired_weekly_hours': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 0, 'step': '0.25', 'placeholder': 'e.g. 19.5',
            }),
            'wants_lunch_break': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'desired_weekly_hours': 'Desired weekly hours',
            'wants_lunch_break': 'I would like a scheduled lunch break',
        }


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
        fields = ['user', 'schedule', 'date', 'start_time', 'end_time']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'schedule': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, scheduler=None, **kwargs):
        super().__init__(*args, **kwargs)
        from account.models import Employee
        from .models import Schedule
        if scheduler:
            managed = Schedule.objects.filter(schedulers=scheduler)
            self.fields['user'].queryset = Employee.objects.filter(
                member_of__in=managed
            ).distinct().order_by('last_name', 'first_name')
            self.fields['schedule'].queryset = managed
        else:
            self.fields['user'].queryset = Employee.objects.all().order_by('last_name', 'first_name')
            self.fields['schedule'].queryset = Schedule.objects.all()

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

class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ['name', 'color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Schedule name'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'roster-color-input'}),
        }

