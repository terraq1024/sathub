from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/projects", include("apps.projects.urls")),
    path("api/ingestion/", include("apps.ingestion.urls")),
    path("api/imagery/", include("apps.imagery.urls")),
    path("api/services/", include("apps.publishing.urls")),
    path("api/stac/", include("apps.stac_api.urls")),
    path("api/access/", include("apps.access_control.urls")),
    path("api/delivery/", include("apps.delivery.urls")),
    path("api/processing/", include("apps.processing.urls")),
    path("api/storage/", include("apps.storage_manager.urls")),
    path("api/metadata/", include("apps.metadata_registry.urls")),
    path("api/catalog/", include("apps.catalog_governance.urls")),
    path("api/audit/", include("apps.audit_log.urls")),
    # Legacy catalog aliases kept for existing internal clients and older tests.
    path("", include("apps.catalog_governance.urls")),
]
