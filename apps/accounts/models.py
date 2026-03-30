from django.contrib.auth.models import  User
from django.db import models

# Create your models here.

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('citizen', 'Citizen'),
        ('officer', 'Officer'),
        ('admin', 'Administrator')
    ]

    SECTOR_CHOICES = [
        ('infrastructure', 'Infrastructure'),
        ('utilities', 'Utilities'),
        ('safety', 'Safety'),
        ('health', 'Health'),
        ('admin', 'Administration')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, blank=True)  # only for officers
    phone = models.CharField(max_length=20, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.role}"