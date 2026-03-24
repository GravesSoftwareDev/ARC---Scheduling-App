from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.

class Employee(AbstractUser):
    class Role(models.TextChoices):
        employee = 'EMPLOYEE','Employee'
        scheduler = 'SCHEDULER','Scheduler'
        admin = 'ADMIN','Admin'
    
    role = models.CharField(
        choices=Role.choices,
        default=Role.employee
    )

