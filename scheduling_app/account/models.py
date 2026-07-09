from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import datetime

class Employee(AbstractUser):
    class Role(models.TextChoices):
        ASSISTANT_I = 'ASSISTANT_I', 'Assistant I'
        ASSISTANT_II = 'ASSISTANT_II', 'Assistant II'
        TUTOR = 'TUTOR', 'Tutor'

    birthdate = models.DateField(null=True, blank=True)
    part_time = models.BooleanField(default=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TUTOR,
    )
    is_admin = models.BooleanField(default=False)
    desired_weekly_hours = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    wants_lunch_break = models.BooleanField(default=False)

    availability_override_until = models.DateField(null=True, blank=True)

    def has_availability_override(self):
        return bool(
            self.availability_override_until
            and self.availability_override_until >= datetime.date.today()
        )
