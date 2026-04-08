from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError

# Create your models here.

class Subject(models.Model):
    class SubjectChoices(models.TextChoices):
        math = 'MTH','Math'
        science = 'SCI','Science'
        speech = 'SPC','Speech'
        writing = 'WRI','Writing'
        accounting = 'ACC','Accounting'
        compsci = 'CIS', 'Computer Science'
        language = 'LAN','Language'
        academic_coach = 'ACD','Academic Coach'
        math_coach = 'MTC','Math Coach'
        aea_coach = 'AEA','AEA - Academic Coach'
    
    code = models.CharField(
        max_length=3,
        choices=SubjectChoices.choices,
        unique=True,
        primary_key=True
    )
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Employee(AbstractUser):
    class Role(models.TextChoices):
        employee = 'EMPLOYEE','Employee'
        scheduler = 'SCHEDULER','Scheduler'
        admin = 'ADMIN','Admin'
    
    class Department(models.TextChoices):
        new = 'NEW', 'New Hire'
        tutor = 'TUT','Tutor'
        arc_assist_one = 'AA1','Arc Assistant I'
        arc_assist_two = 'AA2','Arc Asssistant II'
        supervisor = 'SUP','Supervisor'
        director = 'DIR','Director'

    department = models.CharField(
        max_length=3,
        choices=Department.choices,
        default = Department.new
    )

    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name='employees'
    )
    
    birthdate = models.DateField(null=True, blank=True)
    
    role = models.CharField(
        choices=Role.choices,
        default=Role.employee
    )

class WeeklyAvailability(models.Model):
    class DayOfWeek(models.TextChoices):
        MONDAY = 'MON','Monday'
        TUESDAY = 'TUE','Tuesday'
        WEDNESDAY = 'WED','Wednesday'
        THURSDAY = 'THU','Thursday'
        FRIDAY = 'FRI','Friday'

    class AvailabilityType(models.TextChoices):
        AVAILABLE = 'AVAILABLE','Available'
        PREFERRED = 'PREFERRED','Preferred'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='weekly_availability'
    )
    day_of_week = models.CharField(max_length=3,choices=DayOfWeek.choices)
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
        ordering = ['day_of_week', 'start_time']
        verbose_name_plural = 'Weekly Availabilities'


class OperatingHours(models.Model):
    """Store the tutoring center's operating hours"""
    class DayOfWeek(models.TextChoices):
        MONDAY = 'MON','Monday'
        TUESDAY = 'TUE','Tuesday'
        WEDNESDAY = 'WED','Wednesday'
        THURSDAY = 'THU','Thursday'
        FRIDAY = 'FRI','Friday'
    
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
        ordering = ['day_of_week']
        verbose_name_plural = 'Operating Hours'