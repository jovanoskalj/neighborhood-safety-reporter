from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from apps.accounts.models import UserProfile
from apps.reports.models import Report
from faker import Faker
import random

fake = Faker()

CATEGORIES = ['infrastructure', 'utilities', 'safety', 'health', 'other']
PRIORITIES = ['urgent', 'normal', 'low']
STATUSES = ['new', 'in_progress', 'resolved', 'unclassified']
SECTORS = ['infrastructure', 'utilities', 'safety', 'health', 'admin']
SKOPJE_MUNICIPALITIES = [
    'aerodrom', 'butel', 'gazi_baba', 'gjorche_petrov', 'karposh', 
    'kisela_voda', 'saraj', 'centar', 'chair', 'shuto_orizari'
]

# Skopje coordinates
LAT_RANGE = (41.95, 42.05)
LNG_RANGE = (21.35, 21.55)


class Command(BaseCommand):
    help = 'Seed database with demo data'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database...')

        # Create groups
        for group_name in ['citizen', 'citizens', 'officer', 'officers', 'admin', 'administrators']:
            Group.objects.get_or_create(name=group_name)

        # Create test users
        users = {}
        
        citizen, _ = User.objects.get_or_create(username='demo_citizen')
        citizen.first_name = fake.first_name()
        citizen.last_name = fake.last_name()
        citizen.set_password('citizen123')
        citizen.is_active = True
        citizen.save()
        UserProfile.objects.filter(user=citizen).update(role='citizen')
        citizen.groups.set([Group.objects.get(name='citizen')])

        officer, _ = User.objects.get_or_create(username='demo_officer')
        officer.first_name = fake.first_name()
        officer.last_name = fake.last_name()
        officer.set_password('officer123')
        officer.is_active = True
        officer.is_staff = False
        officer.save()
        UserProfile.objects.filter(user=officer).update(role='officer', sector='safety')
        officer.groups.set([Group.objects.get(name='officer')])

        admin, _ = User.objects.get_or_create(username='demo_admin')
        admin.first_name = fake.first_name()
        admin.last_name = fake.last_name()
        admin.set_password('admin123')
        admin.is_active = True
        admin.is_staff = True
        admin.save()
        UserProfile.objects.filter(user=admin).update(role='admin')
        admin.groups.set([Group.objects.get(name='admin')])

        self.stdout.write('Created 3 users with realistic names: demo_citizen, demo_officer, demo_admin')

        citizens = [citizen, admin]
        reports = []
        for i in range(60):
            reports.append(Report(
                citizen=random.choice(citizens),
                description=fake.paragraph(nb_sentences=3),
                latitude=round(random.uniform(*LAT_RANGE), 6),
                longitude=round(random.uniform(*LNG_RANGE), 6),
                category=random.choice(CATEGORIES),
                priority=random.choice(PRIORITIES),
                municipality=random.choice(SKOPJE_MUNICIPALITIES),
                status=random.choice(STATUSES),
                sector=random.choice(SECTORS),
                assigned_officer=officer if random.random() > 0.5 else None,
            ))

        created = Report.objects.bulk_create(reports, ignore_conflicts=True)
        self.stdout.write(f'bulk_create returned {len(created)} reports')
        self.stdout.write(self.style.SUCCESS('Seeding complete!'))