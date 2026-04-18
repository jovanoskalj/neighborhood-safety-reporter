from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("submit/", views.submit_report, name="submit_report"),
    path("create/", views.create_report, name="create_report"),
    path("<int:report_id>/status/", views.update_report_status, name="update_report_status"),
    path("reclassify/", views.reclassify_reports, name="reclassify_reports"),
]
