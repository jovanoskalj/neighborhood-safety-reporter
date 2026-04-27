from django.urls import path
from .views import (
    login_view, logout_view, profile_view, register_view, verify_email_code_view,
    admin_user_list, admin_user_toggle, admin_user_update_role,
    admin_system_log, admin_category_list,
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
]