from django.db import models
from django.contrib.auth.models import User

class Report(models.Model):
    STATUS_CHOICES = [('new', 'Нова'),
                    ('in_progress', 'Во тек'),
                    ('resolved', 'Завршена'),
                    ('unclassified', 'Некласифицирана'),
                    ('withdrawn', 'Повлечена')]
    
    PRIORITY_CHOICES = [('urgent', 'Итен'),
                        ('normal', 'Нормален'), 
                        ('low', 'Низок')]
    CATEGORY_CHOICES = [('infrastructure', 'Инфраструктура'),
                        ('utilities', 'Комунални услуги'),
                        ('safety', 'Безбедност'),
                        ('health', 'Здравство'), 
                        ('other', 'Друго')]
    SECTOR_CHOICES = [('infrastructure', 'Инфраструктура'),
                      ('utilities', 'Комунални услуги'),
                      ('safety', 'Безбедност'),
                      ('health', 'Здравство'),
                      ('admin', 'Администрација')]

    citizen = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports')
    description = models.TextField()
    image = models.ImageField(upload_to='reports/', blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='other')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, default='admin')
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
        ]

    def __str__(self) -> str:
        return f"Report #{self.pk} ({self.status})"


class ReportStatusHistory(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self) -> str:
        return f"Report #{self.report_id}: {self.from_status or '-'} -> {self.to_status}"