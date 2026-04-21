from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/submit/', views.submit_report, name='submit_report'),
    path('reports/<int:report_id>/status/', views.update_report_status, name='update_report_status'),
    path('reports/heatmap/', views.heatmap, name='heatmap'),
]
