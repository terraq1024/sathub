from django.urls import path

from .views import (
    IngestionItemRetryView,
    IngestionJobDetailView,
    IngestionJobItemsView,
    FolderUploadView,
    ArchiveCheckView,
    IngestionJobListView,
    UrlImportView,
    ZipUploadView,
)


urlpatterns = [
    path("archives/check", ArchiveCheckView.as_view()),
    path("jobs/url-import", UrlImportView.as_view()),
    path("jobs/upload-zip", ZipUploadView.as_view()),
    path("jobs/upload-archive", ZipUploadView.as_view()),
    path("jobs/upload-folder", FolderUploadView.as_view()),
    path("jobs", IngestionJobListView.as_view()),
    path("jobs/<int:job_id>", IngestionJobDetailView.as_view()),
    path("jobs/<int:job_id>/items", IngestionJobItemsView.as_view()),
    path("items/<int:item_id>/retry", IngestionItemRetryView.as_view()),
]
