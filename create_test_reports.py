#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from apps.reports.models import Report

# Get or create test user
user, _ = User.objects.get_or_create(username='testuser', defaults={'email': 'test@example.com'})

# Create test reports in Skopje area
test_reports = [
    {'description': 'Broken street lamp', 'latitude': 41.9981, 'longitude': 21.4254, 'category': 'infrastructure', 'priority': 'urgent', 'status': 'new'},
    {'description': 'Pothole in road', 'latitude': 41.9965, 'longitude': 21.4312, 'category': 'infrastructure', 'priority': 'normal', 'status': 'in_progress'},
    {'description': 'Water leak', 'latitude': 41.9972, 'longitude': 21.4198, 'category': 'utilities', 'priority': 'urgent', 'status': 'new'},
    {'description': 'Trash accumulation', 'latitude': 42.0005, 'longitude': 21.4280, 'category': 'cleanliness', 'priority': 'low', 'status': 'resolved'},
    {'description': 'Dangerous intersection', 'latitude': 41.9945, 'longitude': 21.4350, 'category': 'safety', 'priority': 'urgent', 'status': 'new'},
]

for report_data in test_reports:
    try:
        r = Report.objects.create(citizen=user, **report_data)
        print(f"✓ Created Report #{r.id}: {report_data['description']} (lat: {report_data['latitude']}, lng: {report_data['longitude']})")
    except Exception as e:
        print(f"✗ Error: {e}")

print(f"\nTotal reports: {Report.objects.count()}")
