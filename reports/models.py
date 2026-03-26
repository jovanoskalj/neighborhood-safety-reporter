from django.conf import settings
from django.db import models

# Create your models here.

class Sector(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    
class Report(models.Model):
    STATUs_CHOICES = (
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )   

    description = models.TextField()
    location = models.CharField(max_length=255)
    image = models.ImageField(upload_to='reports/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUs_CHOICES, default='new')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    category = models.CharField(max_length=255)
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)