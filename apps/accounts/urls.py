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
]