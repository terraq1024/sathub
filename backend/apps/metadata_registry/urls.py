from django.urls import path

from .views import DryRunView, ExtractionRunCreateView, OverrideListCreateView, ParserRunDetailView, ParserRunListView, QualityIssueListView, SchemaDetailView, SchemaListCreateView, TemplateDetailView, TemplateListCreateView, TemplateVersionListCreateView, TemplateVersionPublishView


urlpatterns = [
    path("schemas", SchemaListCreateView.as_view()),
    path("schemas/<int:pk>", SchemaDetailView.as_view()),
    path("templates", TemplateListCreateView.as_view()),
    path("templates/<int:pk>", TemplateDetailView.as_view()),
    path("templates/<int:template_id>/versions", TemplateVersionListCreateView.as_view()),
    path("versions/<int:version_id>/publish", TemplateVersionPublishView.as_view()),
    path("runs", ParserRunListView.as_view()),
    path("runs/<int:pk>", ParserRunDetailView.as_view()),
    path("runs/dry-run", DryRunView.as_view()),
    path("runs/execute", ExtractionRunCreateView.as_view()),
    path("quality-issues", QualityIssueListView.as_view()),
    path("overrides", OverrideListCreateView.as_view()),
]
