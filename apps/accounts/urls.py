from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    login_view, logout_view, profile_view, register_view, verify_email_code_view,
    admin_user_list, admin_user_toggle, admin_user_update_role,
    admin_system_log, admin_category_list, admin_dead_emails,
    notifications_list, mark_notification_read, mark_all_notifications_read, delete_notification,
)

urlpatterns = [
    path("register/", register_view, name="register"),
    path("verify-email-code/", verify_email_code_view, name="verify_email_code"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile_view, name="profile"),
    path("admin-panel/users/", admin_user_list, name="admin_user_list"),
    path("admin-panel/users/<int:user_id>/toggle/", admin_user_toggle, name="admin_user_toggle"),
    path("admin-panel/users/<int:user_id>/role/", admin_user_update_role, name="admin_user_update_role"),
    path("admin-panel/system-log/", admin_system_log, name="admin_system_log"),
    path("admin-panel/categories/", admin_category_list, name="admin_category_list"),
    path("admin-panel/dead-emails/", admin_dead_emails, name="admin_dead_emails"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.html",
            html_email_template_name="accounts/password_reset_email_html.html",
            subject_template_name="accounts/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("notifications/", notifications_list, name="notifications_list"),
    path("notifications/<int:notification_id>/read/", mark_notification_read, name="mark_notification_read"),
    path("notifications/mark-all-read/", mark_all_notifications_read, name="mark_all_notifications_read"),
    path("notifications/<int:notification_id>/delete/", delete_notification, name="delete_notification"),
]