from django import forms
from .models import OperatingHours, ScheduleEntry, DateOperatingHours, Schedule


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
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control','placeholder':'Schedule name'})
        }

