from django.urls import path

from .views import AuditEventDetailView, AuditEventListView


app_name = "audit_log"

urlpatterns = [
    path("", AuditEventListView.as_view(), name="event-list"),
    path("<int:pk>", AuditEventDetailView.as_view(), name="event-detail"),
]
