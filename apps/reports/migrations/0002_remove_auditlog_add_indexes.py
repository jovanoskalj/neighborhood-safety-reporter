# Generated manually for project baseline fixes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="AuditLog"),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["status"], name="report_status_idx"),
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["sector"], name="report_sector_idx"),
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["category"], name="report_category_idx"),
        ),
    ]
