from django import forms
from .models import OperatingHours, DateOperatingHours, Schedule, AvailabilityWindow


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


class AvailabilityWindowForm(forms.ModelForm):
    class Meta:
        model = AvailabilityWindow
        fields = ('is_open', 'opens_at', 'closes_at')
        widgets = {
            'opens_at': forms.DateInput(attrs={'type': 'date'}),
            'closes_at': forms.DateInput(attrs={'type': 'date'}),
        }