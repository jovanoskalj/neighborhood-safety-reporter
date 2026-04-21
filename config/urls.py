from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.reports.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("api/analytics/", include("apps.analytics.api_urls")),
    path("verify/", include("verify_email.urls")),
    path("verification/", include("verify_email.urls")),
]
