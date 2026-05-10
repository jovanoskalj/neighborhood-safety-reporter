from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.reports.models import Report


@override_settings(AI_CLASSIFICATION_ENABLED=True)
class CreateReportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="citizen", password="password123")
        self.url = reverse("create_report")

    @patch("apps.reports.signals.classify_report")
    def test_create_report_success_with_ai_classification(self, mock_classify_report):
        mock_classify_report.return_value = {
            "category": "safety",
            "priority": "urgent",
            "sector": "safety",
        }
        self.client.force_login(self.user)

        payload = {
            "description": "There is a large pothole and poor lighting in the street.",
            "latitude": "37.774900",
            "longitude": "-122.419400",
        }
        response = self.client.post(self.url, data=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Report.objects.count(), 1)

        report = Report.objects.first()
        self.assertEqual(report.status, "new")
        self.assertTrue(report.ai_processed)
        self.assertEqual(report.category, "safety")
        self.assertEqual(report.priority, "urgent")
        self.assertEqual(report.sector, "safety")

        body = response.json()
        self.assertEqual(body["status"], "new")
        self.assertEqual(body["category"], "safety")
        self.assertEqual(body["priority"], "urgent")
        self.assertEqual(body["sector"], "safety")

    @patch("apps.reports.signals.classify_report")
    def test_create_report_fails_validation_with_bad_coordinates(self, mock_classify_report):
        self.client.force_login(self.user)
        payload = {
            "description": "Streetlight is not working",
            "latitude": "123.000000",
            "longitude": "-122.419400",
        }

        response = self.client.post(self.url, data=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Report.objects.count(), 0)
        self.assertIn("errors", response.json())
        mock_classify_report.assert_not_called()

    @patch("apps.reports.signals.classify_report")
    def test_create_report_ai_failure_keeps_report_created_and_unclassified(self, mock_classify_report):
        mock_classify_report.side_effect = TimeoutError("AI timeout")
        self.client.force_login(self.user)

        payload = {
            "description": "Garbage has piled up near the market.",
            "latitude": "40.712776",
            "longitude": "-74.005974",
        }
        response = self.client.post(self.url, data=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Report.objects.count(), 1)

        report = Report.objects.first()
        self.assertEqual(report.status, "unclassified")
        self.assertFalse(report.ai_processed)

        body = response.json()
        self.assertEqual(body["status"], "unclassified")

    def test_create_report_requires_authentication(self):
        payload = {
            "description": "Water leakage on main road",
            "latitude": "12.971599",
            "longitude": "77.594566",
        }

        response = self.client.post(self.url, data=payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Report.objects.count(), 0)
