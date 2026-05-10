from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Subject, Department

User = get_user_model()

class PasswordResetRequestForm(forms.Form):
    first_name = forms.CharField(max_length=150, label='First Name')
    last_name = forms.CharField(max_length=150, label='Last Name')
    email = forms.EmailField(label='OTC Email Address')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if not email.endswith('@otc.edu'):
            raise forms.ValidationError('Please enter your OTC email address (@otc.edu).')
        return email


class EditProfileForm(forms.ModelForm):
    birthdate = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'birthdate')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if email and qs.exists():
            raise forms.ValidationError('That email is already in use.')
        return email


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
