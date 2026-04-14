from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/submit/', views.submit_report, name='submit_report'),
    path('map/', views.map_view, name='map_view'),
    path('api/reports/json/', views.reports_json, name='reports_json'),
]
