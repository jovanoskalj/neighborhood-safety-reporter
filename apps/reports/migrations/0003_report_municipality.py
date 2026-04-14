from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_remove_auditlog_add_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="municipality",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["municipality"], name="report_municipality_idx"),
        ),
    ]
