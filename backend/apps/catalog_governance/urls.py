from django.urls import path

from .views import (
    AdministrativeUnitListView,
    AdministrativeUnitTreeView,
    AssociationView,
    ClassificationDetailView,
    ClassificationListCreateView,
    ImageryGovernanceView,
    ImageryIdsQueryView,
    TagDetailView,
    TagListCreateView,
)


urlpatterns = [
    path("administrative-units", AdministrativeUnitListView.as_view()),
    path("administrative-units/tree", AdministrativeUnitTreeView.as_view()),
    path("classifications", ClassificationListCreateView.as_view()),
    path("classifications/<int:classification_id>", ClassificationDetailView.as_view()),
    path("tags", TagListCreateView.as_view()),
    path("tags/<int:tag_id>", TagDetailView.as_view()),
    path("associations", AssociationView.as_view()),
    path("imagery-ids", ImageryIdsQueryView.as_view()),
    path("imagery/<str:imagery_id>", ImageryGovernanceView.as_view()),
]
