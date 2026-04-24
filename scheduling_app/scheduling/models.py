from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.conf import settings
from django.core.exceptions import ValidationError


DAY_ORDER = Case(
    When(day_of_week='MON', then=Value(0)),
    When(day_of_week='TUE', then=Value(1)),
    When(day_of_week='WED', then=Value(2)),
    When(day_of_week='THU', then=Value(3)),
    When(day_of_week='FRI', then=Value(4)),
    output_field=IntegerField(),
)
class DayOfWeek(models.TextChoices):
    MONDAY = 'MON', 'Monday'
    TUESDAY = 'TUE', 'Tuesday'
    WEDNESDAY = 'WED', 'Wednesday'
    THURSDAY = 'THU', 'Thursday'
    FRIDAY = 'FRI', 'Friday'

class WeeklyAvailability(models.Model):

    class AvailabilityType(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        PREFERRED = 'PREFERRED', 'Preferred'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_availability'
    )
    day_of_week = models.CharField(max_length=3, choices=DayOfWeek.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    availability_type = models.CharField(
        max_length=10,
        choices=AvailabilityType.choices,
        default=AvailabilityType.AVAILABLE
    )

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be before end time.")
            overlaps = WeeklyAvailability.objects.filter(
                user=self.user,
                day_of_week=self.day_of_week,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("This block overlaps with an existing availability.")

    def __str__(self):
        return f"{self.user} - {self.day_of_week} {self.start_time}-{self.end_time}"

    class Meta:
        ordering = [DAY_ORDER, 'start_time']
        verbose_name_plural = 'Weekly Availabilities'


class OperatingHours(models.Model):

    day_of_week = models.CharField(
        max_length=3,
        choices=DayOfWeek.choices,
        unique=True
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be before end time.")

    def __str__(self):
        return f"{self.get_day_of_week_display()}: {self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

    class Meta:
        ordering = [DAY_ORDER]
        verbose_name_plural = 'Operating Hours'

class WeeklySchedule(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name = 'scheduled_blocks'
    )
    department = models.ForeignKey(
        'account.Department',
        on_delete=models.PROTECT,
        related_name='scheduled_blocks'
    )
    day_of_week = models.CharField(
        max_length=3, 
        choices=DayOfWeek.choices
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be before end time.")
            
            overlaps = WeeklySchedule.objects.filter(
                user=self.user,
                day_of_week = self.day_of_week,
                start_time__lt = self.end_time,
                end_time__gt = self.start_time,
            ).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("This block overlaps with an existing scheduled block.")
    
    def __str__(self):
        return f'{self.user} = {self.department} - {self.day_of_week} - {self.start_time} - {self.end_time}'

    class Meta:
        ordering = [DAY_ORDER, 'start_time']