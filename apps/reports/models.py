from django.db import models
from django.contrib.auth.models import User

class Report(models.Model):
    STATUS_CHOICES = [('new', 'New'),
                    ('in_progress', 'In Progress'),
                    ('resolved', 'Resolved'),
                    ('unclassified', 'Unclassified')]
    
    PRIORITY_CHOICES = [('urgent', 'Urgent'),
                        ('normal', 'Normal'), 
                        ('low', 'Low')]
    CATEGORY_CHOICES = [('infrastructure', 'Infrastructure'),
                        ('utilities', 'Utilities'),
                        ('safety', 'Safety'),
                        ('health', 'Health'), 
                        ('other', 'Other')]
    SECTOR_CHOICES = [('infrastructure', 'Infrastructure'),
                      ('utilities', 'Utilities'),
                      ('safety', 'Safety'),
                      ('health', 'Health'),
                      ('admin', 'Administration')]

    citizen = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    description = models.TextField()
    image = models.ImageField(upload_to='reports/', blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, default='admin')
    municipality = models.CharField(max_length=120, blank=True, default='')
    assigned_officer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_reports')
    internal_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    ai_processed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["status"], name="report_status_idx"),
            models.Index(fields=["sector"], name="report_sector_idx"),
            models.Index(fields=["category"], name="report_category_idx"),
            models.Index(fields=["municipality"], name="report_municipality_idx"),
        ]

    def __str__(self) -> str:
        return f"Report #{self.pk} ({self.status})"