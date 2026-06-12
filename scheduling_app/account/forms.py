from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
User = get_user_model()

class EditEmployeeForm(forms.ModelForm):
    birthdate = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    part_time = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'birthdate', 'part_time', 'role')


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    birthdate = forms.DateField(required=True)
    part_time = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "birthdate", "part_time", "role")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.birthdate = self.cleaned_data["birthdate"]
        user.role = self.cleaned_data["role"]
        user.part_time = self.cleaned_data["part_time"]
        if commit:
            user.save()
        return user

