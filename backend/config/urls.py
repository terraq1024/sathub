from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/projects", include("apps.projects.urls")),
    path("api/ingestion/", include("apps.ingestion.urls")),
    path("api/imagery/", include("apps.imagery.urls")),
    path("api/stac/", include("apps.stac_api.urls")),
    path("api/storage/", include("apps.storage_manager.urls")),
]
