from django.urls import path

from .views import (
    ImageryAssetView,
    ImageryBatchView,
    ImageryDatasetDetailView,
    ImageryDatasetListCreateView,
    ImageryDatasetMemberDetailView,
    ImageryDatasetMemberListView,
    ImageryDatasetMemberOrderView,
    ImageryDatasetRefreshView,
    ImageryDetailView,
    ImageryFacetsView,
    ImageryListView,
    ImageryMapView,
    ImageryRemoveView,
    ImageryRestoreView,
    ImageryStacView,
    ImagerySavedSearchListCreateView,
    ImagerySavedSearchDetailView,
)


urlpatterns = [
    path("facets", ImageryFacetsView.as_view()),
    path("map", ImageryMapView.as_view()),
    path("batch", ImageryBatchView.as_view()),
    path("datasets", ImageryDatasetListCreateView.as_view()),
    path("datasets/<uuid:dataset_id>", ImageryDatasetDetailView.as_view()),
    path("datasets/<uuid:dataset_id>/refresh", ImageryDatasetRefreshView.as_view()),
    path("datasets/<uuid:dataset_id>/members", ImageryDatasetMemberListView.as_view()),
    path("datasets/<uuid:dataset_id>/members/order", ImageryDatasetMemberOrderView.as_view()),
    path("datasets/<uuid:dataset_id>/members/<str:image_id>", ImageryDatasetMemberDetailView.as_view()),
    path("saved-searches", ImagerySavedSearchListCreateView.as_view()),
    path("saved-searches/<uuid:search_id>", ImagerySavedSearchDetailView.as_view()),
    path("", ImageryListView.as_view()),
    path("<str:image_id>", ImageryDetailView.as_view()),
    path("<str:image_id>/remove", ImageryRemoveView.as_view()),
    path("<str:image_id>/restore", ImageryRestoreView.as_view()),
    path("<str:image_id>/stac", ImageryStacView.as_view()),
    path("<str:image_id>/assets/<str:role>", ImageryAssetView.as_view()),
]
