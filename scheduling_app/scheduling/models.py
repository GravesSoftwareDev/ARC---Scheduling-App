from django.db import models
from django.db.models import Case, IntegerField, Value, When
from django.conf import settings
from django.core.exceptions import ValidationError
import datetime


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

class Schedule(models.Model):
    name = models.CharField(max_length=100, unique=True)
    color = models.CharField(max_length=7, default='#003F7F')
    schedulers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='scheduler_of'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='member_of'
    )

    def __str__(self):
        return self.name
    
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
    schedule = models.ForeignKey(
        'Schedule',
        on_delete=models.PROTECT,
        related_name = 'scheduled_blocks',
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

class ScheduleEntry(models.Model):
    """A specific dated shift assigned to an employee."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedule_entries'
    )
    schedule = models.ForeignKey(
        'Schedule',
        on_delete=models.PROTECT,
        related_name='schedule_entries',
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=50, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_schedule_entries'
    )

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be before end time.")
            overlaps = ScheduleEntry.objects.filter(
                user=self.user,
                date=self.date,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlaps.exists():
                raise ValidationError("This shift overlaps with an existing schedule entry.")

    def __str__(self):
        return f"{self.user} – {self.schedule} on {self.date} {self.start_time}–{self.end_time}"

    class Meta:
        ordering = ['date', 'start_time']


class DateOperatingHours(models.Model):
    """Date-specific operating hours override. Falls back to OperatingHours weekly defaults."""
    date = models.DateField(unique=True)
    is_closed = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    def clean(self):
        if not self.is_closed:
            if not self.start_time or not self.end_time:
                raise ValidationError("Start and end time are required when not closed.")
            if self.start_time >= self.end_time:
                raise ValidationError("Start time must be before end time.")

    def __str__(self):
        if self.is_closed:
            return f"{self.date} – Closed ({self.note})"
        return f"{self.date}: {self.start_time.strftime('%I:%M %p')} – {self.end_time.strftime('%I:%M %p')}"

    class Meta:
        ordering = ['date']
        verbose_name_plural = 'Date Operating Hours'