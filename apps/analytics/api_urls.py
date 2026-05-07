from django.urls import path

from . import views

app_name = "api_analytics"

urlpatterns = [
    path("stats/", views.stats, name="stats"),
    path("kpi/", views.kpi_metrics, name="kpi"),
]
