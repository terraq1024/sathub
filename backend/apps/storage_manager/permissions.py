from rest_framework.permissions import BasePermission


class IsStorageUser(BasePermission):
    """Any logged-in user may register storage endpoints; object-level
    checks scope each endpoint to its creator (staff see everything)."""

    message = "请先登录。"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
