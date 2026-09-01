from django.urls import path

from .ogc_tiles import OGCServiceLandingView, OGCTileView, OGCTilesetMetadataView, OGCTilesetsView
from .views import ImageryServiceDetailView, ImageryServiceListCreateView, OfflineServiceView, PublishServiceView, ServiceJobsView, ServiceTileJSONView, ServiceTileView


urlpatterns = [
    path("", ImageryServiceListCreateView.as_view()),
    path("<slug:service_key>", ImageryServiceDetailView.as_view()),
    path("<slug:service_key>/publish", PublishServiceView.as_view()),
    path("<slug:service_key>/offline", OfflineServiceView.as_view()),
    path("<slug:service_key>/jobs", ServiceJobsView.as_view()),
    path("<slug:service_key>/tilejson", ServiceTileJSONView.as_view()),
    path("<slug:service_key>/tiles/<int:z>/<int:x>/<int:y>.png", ServiceTileView.as_view()),
    path("<slug:service_key>/ogcapi", OGCServiceLandingView.as_view()),
    path("<slug:service_key>/ogcapi/tiles", OGCTilesetsView.as_view()),
    path("<slug:service_key>/ogcapi/tiles/<str:tile_matrix_set>", OGCTilesetMetadataView.as_view()),
    path("<slug:service_key>/ogcapi/tiles/<str:tile_matrix_set>/<int:tile_matrix>/<int:tile_row>/<int:tile_col>", OGCTileView.as_view()),
    path("<slug:service_key>/ogcapi/tiles/<str:tile_matrix_set>/<int:tile_matrix>/<int:tile_row>/<int:tile_col>.png", OGCTileView.as_view()),
]
