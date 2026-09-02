from django.urls import path

from .views import (
    EndpointCheckView,
    EndpointDetailView,
    EndpointListCreateView,
    EndpointScanView,
    EndpointIngestView,
    ObjectListView,
    ObjectDetailView,
    ScanJobDetailView,
    ScanJobListView,
)

urlpatterns = [
    path("endpoints", EndpointListCreateView.as_view()),
    path("endpoints/<uuid:endpoint_id>", EndpointDetailView.as_view()),
    path("endpoints/<uuid:endpoint_id>/check", EndpointCheckView.as_view()),
    path("endpoints/<uuid:endpoint_id>/scan", EndpointScanView.as_view()),
    path("endpoints/<uuid:endpoint_id>/ingest", EndpointIngestView.as_view()),
    path("scan-jobs", ScanJobListView.as_view()),
    path("scan-jobs/<uuid:job_id>", ScanJobDetailView.as_view()),
    path("objects", ObjectListView.as_view()),
    path("objects/<uuid:object_id>", ObjectDetailView.as_view()),
]
