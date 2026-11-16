from django import forms
from django.contrib.auth import get_user_model
from scheduling.models import Schedule, Term
from .models import SecuritySettings
User = get_user_model()

# Birthday is month + day only (no year) — see Employee.birth_month/birth_day.
# Day-vs-month validity (e.g. no April 31) is checked in Employee.clean().
BIRTH_MONTH_CHOICES = [('', 'Month')] + User._meta.get_field('birth_month').choices
BIRTH_DAY_CHOICES = [('', 'Day')] + [(d, d) for d in range(1, 32)]


def birth_month_field(required):
    return forms.TypedChoiceField(choices=BIRTH_MONTH_CHOICES, coerce=int,
                                  empty_value=None, required=required)


def birth_day_field(required):
    return forms.TypedChoiceField(choices=BIRTH_DAY_CHOICES, coerce=int,
                                  empty_value=None, required=required)


def override_term_field():
    return forms.ChoiceField(choices=[('', 'Term')] + Term.choices, required=False)


def override_year_field():
    return forms.IntegerField(required=False, min_value=2000, max_value=2100,
                              widget=forms.NumberInput(attrs={'placeholder': 'Year'}))


def clean_availability_override(form, cleaned):
    """An exception date needs the term it applies to; without a date, any
    term/year is dropped so stale values don't linger."""
    if cleaned.get('availability_override_until'):
        if not cleaned.get('availability_override_term'):
            form.add_error('availability_override_term', 'Choose the term this exception applies to.')
        if not cleaned.get('availability_override_year'):
            form.add_error('availability_override_year', 'Enter the year of the term this exception applies to.')
    else:
        cleaned['availability_override_term'] = ''
        cleaned['availability_override_year'] = None
    return cleaned


class EditEmployeeForm(forms.ModelForm):
    birth_month = birth_month_field(required=False)
    birth_day = birth_day_field(required=False)
    part_time = forms.BooleanField(required=False)
    role = forms.ChoiceField(choices=User.Role.choices, required=True)
    is_admin = forms.BooleanField(required=False)
    availability_override_until = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )
    availability_override_term = override_term_field()
    availability_override_year = override_year_field()

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'birth_month', 'birth_day',
                   'part_time', 'role', 'is_admin', 'availability_override_until',
                   'availability_override_term', 'availability_override_year')

    def clean(self):
        return clean_availability_override(self, super().clean())


class RegistrationForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    birth_month = birth_month_field(required=True)
    birth_day = birth_day_field(required=True)
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
    availability_override_term = override_term_field()
    availability_override_year = override_year_field()

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "birth_month", "birth_day", "part_time", "role", "is_admin")

    def __init__(self, *args, requester=None, **kwargs):
        super().__init__(*args, **kwargs)
        if requester is not None and not requester.is_admin:
            # Non-admin schedulers can only register employees onto schedules
            # they themselves manage, and can't grant admin privileges.
            self.fields['schedules'].queryset = requester.scheduler_of.order_by('name')
            del self.fields['is_admin']

    def clean(self):
        return clean_availability_override(self, super().clean())

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.birth_month = self.cleaned_data["birth_month"]
        user.birth_day = self.cleaned_data["birth_day"]
        user.role = self.cleaned_data["role"]
        user.part_time = self.cleaned_data["part_time"]
        user.is_admin = self.cleaned_data.get("is_admin", False)
        user.availability_override_until = self.cleaned_data.get("availability_override_until")
        user.availability_override_term = self.cleaned_data.get("availability_override_term", '')
        user.availability_override_year = self.cleaned_data.get("availability_override_year")
        # New employees always start on the shared org-wide default password
        # (editable on Employee List) rather than a random/emailed one — this
        # app has no outbound email, so there's no way to deliver a random
        # password to the new employee.
        user.set_password(SecuritySettings.load().default_password)
        if commit:
            user.save()
        return user

