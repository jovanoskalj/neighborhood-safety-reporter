from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/submit/', views.submit_report, name='submit_report'),

    path('map/', views.map_view, name='map_view'),
    path('api/reports/json/', views.reports_json, name='reports_json'),

    path('reports/<int:report_id>/status/', views.update_report_status, name='update_report_status'),
    path('officer/', views.officer_panel, name='officer_panel'),
    path('reports/export/', views.export_reports, name='export_reports'),
]

