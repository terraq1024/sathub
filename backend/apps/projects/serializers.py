from rest_framework import serializers

from .models import Project, ProjectMembership


class ProjectMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ["id", "user", "username", "role", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    memberships = ProjectMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "code",
            "description",
            "created_by",
            "created_by_username",
            "memberships",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by"]
