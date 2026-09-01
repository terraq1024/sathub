from django.urls import path
from .views import BasketItemView, BasketView, DownloadView, ExportDetailView, ExportListCreateView, SnapshotDetailView, SnapshotListCreateView

urlpatterns = [
    path("basket", BasketView.as_view()),
    path("basket/clear", BasketView.as_view()),
    path("basket/items/<str:image_id>", BasketItemView.as_view()),
    path("exports", ExportListCreateView.as_view()),
    path("exports/<uuid:job_id>", ExportDetailView.as_view()),
    path("snapshots", SnapshotListCreateView.as_view()),
    path("snapshots/<uuid:snapshot_id>", SnapshotDetailView.as_view()),
    path("downloads/<uuid:job_id>", DownloadView.as_view()),
]
