from django.db.models import Q

from .models import Project


def accessible_projects_for(user):
    if user.is_staff or user.is_superuser:
        return Project.objects.all()
    return Project.objects.filter(Q(created_by=user) | Q(memberships__user=user)).distinct()


def user_can_access_project(user, project):
    if user.is_staff or user.is_superuser:
        return True
    return project.created_by_id == user.id or project.memberships.filter(user=user).exists()
