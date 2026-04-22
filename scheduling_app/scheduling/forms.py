from django import forms
from .models import OperatingHours


class OpenHoursForm(forms.ModelForm):
    class Meta:
        model = OperatingHours
        fields = ['start_time', 'end_time']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'time-input'}),
        }
