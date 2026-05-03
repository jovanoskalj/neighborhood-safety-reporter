"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", include("apps.reports.urls")),
    path("admin/", admin.site.urls),
    path("reports/", include("apps.reports.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("api/analytics/", include("apps.analytics.api_urls")),
    path("verify/", include("verify_email.urls")),
    path("verification/", include("verify_email.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass