from django import forms
from .models import DateOperatingHours, DayOfWeek, Schedule, AvailabilityWindow, validate_quarter_hour


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


# Native time pickers step in 15-minute increments (900 s); the model
# validator (validate_quarter_hour) enforces it server-side.
QUARTER_HOUR_TIME_INPUT = {'type': 'time', 'class': 'time-input', 'step': 900}


class WeeklyHoursForm(forms.Form):
    """One open/close pair per weekday for a single role ('' = Default).
    Fields are named <DAY>_start / <DAY>_end, e.g. MON_start."""

    def __init__(self, *args, initial_hours=None, **kwargs):
        super().__init__(*args, **kwargs)
        initial_hours = initial_hours or {}
        for day_code, _label in DayOfWeek.choices:
            start, end = initial_hours.get(day_code, (None, None))
            for suffix, value in (('start', start), ('end', end)):
                self.fields[f'{day_code}_{suffix}'] = forms.TimeField(
                    initial=value,
                    validators=[validate_quarter_hour],
                    widget=forms.TimeInput(attrs=QUARTER_HOUR_TIME_INPUT, format='%H:%M'),
                )

    def clean(self):
        cleaned = super().clean()
        for day_code, label in DayOfWeek.choices:
            start, end = cleaned.get(f'{day_code}_start'), cleaned.get(f'{day_code}_end')
            if start and end and start >= end:
                self.add_error(f'{day_code}_end', f"{label}: close must be after open.")
        return cleaned

    def days(self):
        """[(label, start BoundField, end BoundField)] for the template."""
        return [
            (label, self[f'{code}_start'], self[f'{code}_end'])
            for code, label in DayOfWeek.choices
        ]

    def hours(self):
        """{day_code: (start, end)} from cleaned_data."""
        return {
            code: (self.cleaned_data[f'{code}_start'], self.cleaned_data[f'{code}_end'])
            for code, _label in DayOfWeek.choices
        }


class DateOperatingHoursForm(forms.ModelForm):
    class Meta:
        model = DateOperatingHours
        fields = ['date', 'is_closed', 'start_time', 'end_time', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs=QUARTER_HOUR_TIME_INPUT),
            'end_time': forms.TimeInput(attrs=QUARTER_HOUR_TIME_INPUT),
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