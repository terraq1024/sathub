from rest_framework import generics

from .serializers import ProjectSerializer
from .services import accessible_projects_for


class ProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return accessible_projects_for(self.request.user).prefetch_related("memberships", "memberships__user")
