from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("submit/", views.submit_report, name="submit_report"),
    path("create/", views.create_report, name="create_report"),
    path("<int:report_id>/status/", views.update_report_status, name="update_report_status"),
    path('heatmap/', views.heatmap, name='heatmap'),
    path('map/', views.map_view, name='map_view'),
    path('api/reports/json/', views.reports_json, name='reports_json'),
    path('officer/', views.officer_panel, name='officer_panel'),
    path('dashboard/users/create/', views.create_user, name='create_user'),
    path('dashboard/users/<int:user_id>/toggle/', views.toggle_user_active, name='toggle_user_active'),
    path('dashboard/users/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('dashboard/categories/create/', views.create_category, name='create_category'),
    path('dashboard/categories/<int:category_id>/update/', views.update_category, name='update_category'),
    path('dashboard/categories/<int:category_id>/delete/', views.delete_category, name='delete_category'),
    path('dashboard/sectors/create/', views.create_sector, name='create_sector'),
    path('dashboard/sectors/<int:sector_id>/update/', views.update_sector, name='update_sector'),
    path('dashboard/sectors/<int:sector_id>/delete/', views.delete_sector, name='delete_sector'),
    path('dashboard/export/', views.export_reports_csv, name='export_reports_csv'),
    path('dashboard/import/', views.import_reports_stub, name='import_reports_stub'),
    path('search/', views.search_page, name='search_page'),

]
