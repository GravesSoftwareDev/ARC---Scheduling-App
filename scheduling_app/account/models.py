from django.db import models
from django.contrib.auth.models import AbstractUser

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

