from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from scheduling.models import Schedule
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


class RegistrationForm(UserCreationForm):
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
        if commit:
            user.save()
        return user

