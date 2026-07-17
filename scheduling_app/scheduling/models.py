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
    """A department/team (e.g. "Math", "Assistant I"). `members` can be
    assigned shifts on it; `schedulers` (plus admins) can build its schedule.
    Schedules named to match a Role (see signals.py) auto-sync membership."""
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
    """An employee's recurring weekly availability (no specific date — just a
    day of week + time range). This is what the Schedule Builder checks
    proposed shifts against; it's unrelated to any specific week's shifts,
    which live in ScheduleEntry instead."""

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

class AvailabilityWindow(models.Model):
    """Global on/off switch (with optional date range) for editing availability."""
    is_open = models.BooleanField(default=True)
    opens_at = models.DateField(null=True, blank=True)
    closes_at = models.DateField(null=True, blank=True)

    def clean(self):
        if self.opens_at and self.closes_at and self.opens_at > self.closes_at:
            raise ValidationError("Opens date must be before closes date.")
    
    def is_currently_open(self):
        """Open when the manual toggle is on, OR when today falls within the
        optional date range (the two are independent — either one is enough)."""
        if self.is_open:
            return True
        if self.opens_at or self.closes_at:
            today = datetime.date.today()
            if self.opens_at and today < self.opens_at:
                return False
            if self.closes_at and today > self.closes_at:
                return False
            return True
        return False
    
    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
    
    def __str__(self):
        return f"Availability editing {'open' if self.is_open else 'closed'}."
    
    class Meta:
        verbose_name_plural = 'Availability Window'
    
    
class OperatingHours(models.Model):
    """Weekly default open/close hours, one row per weekday. A date that has
    a matching DateOperatingHours row uses that instead (holidays, one-off
    closures) — see DateOperatingHours below."""

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
    """The recurring, dateless default-week template for a Schedule (day of
    week + times, no specific date) — the starting point "Load Default Week"
    copies into a real week. Not to be confused with ScheduleEntry, which is
    an actual dated shift copied *from* this template (or painted directly)."""
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
    # May hold several ShiftLabel names joined by ", " (schedule builder lets
    # a supervisor tag one employee/slot with multiple position labels).
    custom_label = models.CharField(max_length=255, blank=True, default='')

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
        return f'{self.user} – {self.schedule} - {self.day_of_week} - {self.start_time} - {self.end_time}'

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
    # May hold several ShiftLabel names joined by ", " — see WeeklySchedule.custom_label.
    custom_label = models.CharField(max_length=255, blank=True, default='')
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


# Candidate colors for new ShiftLabels: schedule_labels() (views.py) picks
# the first entry not already used by another label on the same schedule.
# Unrelated to employee colors, which come from a separate EMPLOYEE_PALETTE
# constant in views.py.
LABEL_PALETTE = [
    '#FF3B30',  # red
    '#FF9500',  # orange
    '#FFCC00',  # yellow
    '#34C759',  # green
    '#00C7BE',  # teal
    '#007AFF',  # blue
    '#5856D6',  # indigo
    '#BF5AF2',  # purple
    '#FF2D92',  # hot pink
    '#A2845E',  # brown
    '#FF6B35',  # coral
    '#C8F709',  # lime
    '#64D2FF',  # light blue
    '#AC39AC',  # magenta
    '#FFD60A',  # gold
    '#32ADE6',  # azure
    '#6AC4DC',  # powder blue
    '#30D158',  # mint
    '#FF453A',  # vermillion
    '#A0522D',  # sienna
]


class ShiftLabel(models.Model):
    """A named position/role label (e.g. "WC", "Front Desk") shared across all employees in a schedule."""
    schedule = models.ForeignKey(
        'Schedule',
        on_delete=models.CASCADE,
        related_name='shift_labels'
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7)

    class Meta:
        unique_together = ['schedule', 'name']
        ordering = ['name']

    def __str__(self):
        return f"{self.schedule} – {self.name}"


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