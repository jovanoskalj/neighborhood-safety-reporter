from django.urls import path

from .views import login_view, logout_view, profile_view, register_view, verify_email_code_view

urlpatterns = [
    path("register/", register_view, name="register"),
    path("verify-email-code/", verify_email_code_view, name="verify_email_code"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile_view, name="profile"),
]