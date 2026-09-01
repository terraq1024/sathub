from django.urls import path

from .views import (
    ProcessingJobDetailView,
    ProcessingJobDownloadView,
    ProcessingJobListCreateView,
    ProcessingJobRetryView,
)


urlpatterns = [
    path("jobs", ProcessingJobListCreateView.as_view(), name="processing-job-list"),
    path(
        "jobs/<uuid:job_id>",
        ProcessingJobDetailView.as_view(),
        name="processing-job-detail",
    ),
    path(
        "jobs/<uuid:job_id>/retry",
        ProcessingJobRetryView.as_view(),
        name="processing-job-retry",
    ),
    path(
        "jobs/<uuid:job_id>/download",
        ProcessingJobDownloadView.as_view(),
        name="processing-job-download",
    ),
]
