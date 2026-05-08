from django.urls import path

from . import views

urlpatterns = [
    path("", views.notifications_log, name="notifications_log"),
    path("<int:notification_id>/retry/", views.retry, name="notifications_retry"),
    path("retry-all-failed/", views.retry_all_failed, name="notifications_retry_all_failed"),
    path("bulk-notify/", views.bulk_notify_preview, name="notifications_bulk_notify"),
    path("bulk-notify/send/", views.bulk_notify_send, name="notifications_bulk_notify_send"),

]
