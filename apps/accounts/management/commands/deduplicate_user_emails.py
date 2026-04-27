"""Normalize duplicate user emails to avoid verification-token ambiguity."""

from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """De-duplicate auth users by email while preserving one canonical account."""

    help = "Find duplicate email addresses in auth_user and keep only one canonical account per email."

    def handle(self, *args, **options):
        by_email: dict[str, list[User]] = defaultdict(list)
        for user in User.objects.exclude(email="").order_by("id"):
            by_email[user.email.strip().lower()].append(user)

        changed = 0
        duplicates = 0

        for email_key, users in by_email.items():
            if len(users) <= 1:
                continue
            duplicates += 1

            # Keep priority: superuser > active > oldest id
            users_sorted = sorted(users, key=lambda u: (not u.is_superuser, not u.is_active, u.id))
            keep = users_sorted[0]

            for duplicate in users_sorted[1:]:
                original = duplicate.email
                local, at, domain = original.partition("@")
                if at:
                    duplicate.email = f"{local}+dup{duplicate.id}@{domain}"
                else:
                    duplicate.email = f"{original}+dup{duplicate.id}"
                duplicate.is_active = False
                duplicate.save(update_fields=["email", "is_active"])
                changed += 1

                self.stdout.write(
                    self.style.WARNING(
                        f"Updated user #{duplicate.id} ({duplicate.username}) email from {original} to {duplicate.email}."
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Kept user #{keep.id} ({keep.username}) as canonical for {email_key}."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Duplicate groups: {duplicates}. Updated users: {changed}."
            )
        )
