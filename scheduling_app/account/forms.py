from django import forms
from django.contrib.auth import get_user_model
from scheduling.models import Schedule
from .models import SecuritySettings
User = get_user_model()


class EditEmployeeForm(forms.ModelForm):
    birthdate = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    part_time = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)
    is_admin = forms.BooleanField(required=False)
    availability_override_until = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'birthdate',
                   'part_time', 'role', 'is_admin', 'availability_override_until')


class RegistrationForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    birthdate = forms.DateField(required=True)
    part_time = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)
    is_admin = forms.BooleanField(required=False)
    schedules = forms.ModelMultipleChoiceField(
        queryset=Schedule.objects.order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    availability_override_until = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "birthdate", "part_time", "role", "is_admin")

    def __init__(self, *args, requester=None, **kwargs):
        super().__init__(*args, **kwargs)
        if requester is not None and not requester.is_admin:
            # Non-admin schedulers can only register employees onto schedules
            # they themselves manage, and can't grant admin privileges.
            self.fields['schedules'].queryset = requester.scheduler_of.order_by('name')
            del self.fields['is_admin']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.birthdate = self.cleaned_data["birthdate"]
        user.role = self.cleaned_data["role"]
        user.part_time = self.cleaned_data["part_time"]
        user.is_admin = self.cleaned_data.get("is_admin", False)
        user.availability_override_until = self.cleaned_data.get("availability_override_until")
        # New employees always start on the shared org-wide default password
        # (editable on Employee List) rather than a random/emailed one — this
        # app has no outbound email, so there's no way to deliver a random
        # password to the new employee.
        user.set_password(SecuritySettings.load().default_password)
        if commit:
            user.save()
        return user

