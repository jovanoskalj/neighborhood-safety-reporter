from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.

class User(AbstractUser):
    ROLE_CHOICES = (
        ('citizen', 'Citizen'),
        ('officer', 'Officer'),
        ('admin', 'Admin'), 
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.username