from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from scheduling.models import Schedule

User = get_user_model()

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    birthdate = forms.DateField(required=True)
    schedules = forms.ModelMultipleChoiceField(queryset=Schedule.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "birthdate", "schedules", "role")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.birthdate = self.cleaned_data["birthdate"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
            for schedule in self.cleaned_data["schedules"]:
                schedule.members.add(user)
        return user
