from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import datetime

class Employee(AbstractUser):
    class Role(models.TextChoices):
        ASSISTANT_I = 'ASSISTANT_I', 'Assistant I'
        ASSISTANT_II = 'ASSISTANT_II', 'Assistant II'
        TUTOR = 'TUTOR', 'Tutor'
        LIBRARY = 'LIBRARY','Library Staff'

    birthdate = models.DateField(null=True, blank=True)
    part_time = models.BooleanField(default=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TUTOR,
    )
    # App-level admin flag — deliberately separate from Django's own
    # is_staff/is_superuser (which only control the built-in /admin/ site).
    # This is what every admin-only screen in the app itself checks.
    is_admin = models.BooleanField(default=False)
    desired_weekly_hours = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    wants_lunch_break = models.BooleanField(default=False)

    # If set to a future date, this employee can edit their own availability
    # even while the global AvailabilityWindow is closed to everyone else.
    availability_override_until = models.DateField(null=True, blank=True)

    def has_availability_override(self):
        return bool(
            self.availability_override_until
            and self.availability_override_until >= datetime.date.today()
        )


class SecuritySettings(models.Model):
    """Singleton (always pk=1) holding the shared default password newly
    registered employees get, and what "Reset Password" resets them back to."""
    default_password = models.CharField(max_length=128, default='Test123!')

    def save(self, *args, **kwargs):
        # Force every save to the same row so this table never has more than
        # one settings object, regardless of how it's constructed/saved.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Deletion is a no-op — the singleton row should always exist so
        # SecuritySettings.load() never has to handle a missing settings object.
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
