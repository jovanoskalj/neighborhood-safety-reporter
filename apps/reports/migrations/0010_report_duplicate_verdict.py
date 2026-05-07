# Generated manually for duplicate admin review workflow

from django.db import migrations, models


def set_pending_for_existing_duplicates(apps, schema_editor):
    Report = apps.get_model("reports", "Report")
    Report.objects.filter(is_duplicate=True).update(duplicate_verdict="pending")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0009_populate_sectors"),
    ]

    operations = [
        migrations.AddField(
            model_name="report",
            name="duplicate_verdict",
            field=models.CharField(
                choices=[
                    ("none", "Нема"),
                    ("pending", "Чека одлука на админ"),
                    ("confirmed", "Потврден дупликат"),
                    ("rejected", "Не е дупликат"),
                ],
                default="none",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="report",
            index=models.Index(fields=["duplicate_verdict"], name="report_dup_verdict_idx"),
        ),
        migrations.RunPython(set_pending_for_existing_duplicates, noop_reverse),
    ]
