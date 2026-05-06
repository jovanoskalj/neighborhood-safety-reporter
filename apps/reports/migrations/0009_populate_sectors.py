# Generated migration to populate initial sectors and categories

from django.db import migrations


def populate_sectors_and_categories(apps, schema_editor):
    """Populate default sectors and categories based on SECTOR_CHOICES and CATEGORY_CHOICES."""
    Sector = apps.get_model('reports', 'Sector')
    ReportCategory = apps.get_model('reports', 'ReportCategory')
    
    sectors = [
        ('infrastructure', 'Инфраструктура'),
        ('utilities', 'Комунални услуги'),
        ('safety', 'Безбедност'),
        ('health', 'Здравство'),
        ('admin', 'Администрација'),
    ]
    
    categories = [
        ('infrastructure', 'Инфраструктура'),
        ('utilities', 'Комунални услуги'),
        ('safety', 'Безбедност'),
        ('health', 'Здравство'),
        ('other', 'Друго'),
    ]
    
    for key, name in sectors:
        Sector.objects.get_or_create(
            key=key,
            defaults={'name': name, 'is_active': True}
        )
    
    for key, name in categories:
        ReportCategory.objects.get_or_create(
            key=key,
            defaults={'name': name, 'is_active': True}
        )


def reverse_populate(apps, schema_editor):
    """Remove populated sectors and categories."""
    Sector = apps.get_model('reports', 'Sector')
    ReportCategory = apps.get_model('reports', 'ReportCategory')
    Sector.objects.filter(key__in=['infrastructure', 'utilities', 'safety', 'health', 'admin']).delete()
    ReportCategory.objects.filter(key__in=['infrastructure', 'utilities', 'safety', 'health', 'other']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0008_merge_20260501_1815'),
    ]

    operations = [
        migrations.RunPython(populate_sectors_and_categories, reverse_populate),
    ]
