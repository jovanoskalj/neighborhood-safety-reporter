from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/submit/', views.submit_report, name='submit_report'),
    path('reports/export/', views.export_reports, name='export_reports'),
]