from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Retry failed email notifications'

    def handle(self, *args, **kwargs):
        from apps.notifications.models import Notification
        from apps.notifications.sender import send_status_notification

        MAX_RETRIES = 3
        failed = Notification.objects.filter(
            status='failed',
            retry_count__lt=MAX_RETRIES
        )

        total = failed.count()
        retried = 0
        succeeded = 0
        still_failed = 0

        self.stdout.write(f'Found {total} failed notifications to retry...')

        for notification in failed:
            try:
                send_status_notification(notification.report, notification.report.citizen)
                notification.status = 'sent'
                notification.retry_count += 1
                notification.save()
                succeeded += 1
            except Exception as e:
                notification.retry_count += 1
                if notification.retry_count >= MAX_RETRIES:
                    notification.status = 'dead'
                notification.save()
                still_failed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Retried: {retried+succeeded+still_failed}, Succeeded: {succeeded}, Still failed: {still_failed}'
        ))