from django.urls import path
from . import views

urlpatterns = [
    path('my-reports/', views.my_reports, name='my_reports'),
    path('new-report/', views.new_report, name='new_report'),
]