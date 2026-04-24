from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Subject, Department

User = get_user_model()

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    birthdate = forms.DateField(required=True)
    departments = forms.ModelMultipleChoiceField(queryset=Department.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    subjects = forms.ModelMultipleChoiceField(queryset=Subject.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "birthdate", "departments", "subjects", "role")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.birthdate = self.cleaned_data["birthdate"]
        user.role = self.cleaned_data["role"]
        if commit:
            user.save()
            user.subjects.set(self.cleaned_data["subjects"])
            user.departments.set(self.cleaned_data["departments"])
        return user
