"""
Management command: send_resolved_notifications
Task T-305 — Bulk email to citizens in a region about resolved issues.

Usage:
    python manage.py send_resolved_notifications
    python manage.py send_resolved_notifications --municipality strumica
    python manage.py send_resolved_notifications --sector safety
    python manage.py send_resolved_notifications --dry-run
"""

import logging

from django.core.management.base import BaseCommand

from apps.notifications.senders import send_bulk_resolved_email
from apps.reports.models import Report

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send bulk email notifications to citizens for resolved reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--municipality",
            type=str,
            default=None,
            help="Filter by municipality key (e.g. 'strumica', 'bitola').",
        )
        parser.add_argument(
            "--sector",
            type=str,
            default=None,
            help="Filter by sector key (e.g. 'safety', 'health').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview without actually sending.",
        )

    def handle(self, *args, **options):
        municipality = options["municipality"]
        sector       = options["sector"]
        dry_run      = options["dry_run"]

        qs = (
            Report.objects
            .filter(status="resolved")
            .exclude(citizen__email="")
            .select_related("citizen")
        )

        if municipality:
            qs = qs.filter(municipality=municipality)
        if sector:
            qs = qs.filter(sector=sector)

        total = qs.count()

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN] Би се испратиле {total} известувања"
                + (f" | општина: {municipality}" if municipality else "")
                + (f" | сектор: {sector}"        if sector        else "")
            ))
            return

        if total == 0:
            self.stdout.write(self.style.WARNING(
                "Нема резолвирани пријави за избраните филтри."
            ))
            return

        self.stdout.write(f"Испраќање на {total} известувања...")

        succeeded = 0
        failed    = 0

        for report in qs:
            n = send_bulk_resolved_email(report)
            if n and n.status == "sent":
                succeeded += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ #{report.pk} → {report.citizen.email}"
                ))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f"  ✗ #{report.pk} → {report.citizen.email}"
                ))

        self.stdout.write("\n" + "=" * 45)
        self.stdout.write(self.style.SUCCESS(f"Успешно:  {succeeded}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"Неуспешно: {failed}"))
        self.stdout.write(f"Вкупно:   {total}")