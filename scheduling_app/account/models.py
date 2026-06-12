from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
        
class Employee(AbstractUser):
    class Role(models.TextChoices):
        tutor = 'TUTOR','Tutor'
        arc_assistant = 'ARC_ASSISTANT','ARC Assistant'
        admin = 'ADMIN','Admin'
    
    birthdate = models.DateField(null=True, blank=True)
    part_time = models.BooleanField(default=True)
    role = models.CharField(
        choices=Role.choices,
        default=Role.tutor
    )

