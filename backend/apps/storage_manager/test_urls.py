from django.urls import include, path


urlpatterns = [path("api/storage/", include("apps.storage_manager.urls"))]
