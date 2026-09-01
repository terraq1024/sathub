from rest_framework import generics, permissions

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventQuerysetMixin:
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        queryset = AuditEvent.objects.select_related("actor")
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset
        return queryset.filter(actor=user)


class AuditEventListView(AuditEventQuerysetMixin, generics.ListAPIView):
    pass


class AuditEventDetailView(AuditEventQuerysetMixin, generics.RetrieveAPIView):
    pass
