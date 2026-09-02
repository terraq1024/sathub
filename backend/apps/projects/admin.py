from django.contrib import admin

from .models import Project, ProjectMembership


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "code", "created_by", "created_at"]
    search_fields = ["name", "code", "description"]
    list_filter = ["created_at"]


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "user", "role", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["project__name", "project__code", "user__username"]
