from django.urls import path

from apps.reports.views import create_report

urlpatterns = [
    path("", create_report, name="create_report"),
]
