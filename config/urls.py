from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.reports.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("verify/", include("verify_email.urls")),
    path("verification/", include("verify_email.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
