from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/', views.reports_api, name='reports_api'),
    path('reports/submit/', views.submit_report, name='submit_report'),
    path('reports/my/', views.my_reports, name='my_reports'),
    path('reports/<int:report_id>/', views.report_detail, name='report_detail'),
    path('reports/<int:report_id>/withdraw/', views.withdraw_report, name='withdraw_report'),
    path('reports/map/', views.map_view, name='reports_map'),
    path('reports/heatmap/', views.heatmap_data, name='reports_heatmap'),
    path('reports/<int:report_id>/status/', views.update_report_status, name='update_report_status'),
]
