from rest_framework.permissions import BasePermission


class IsStorageAdmin(BasePermission):
    message = "只有管理员可以管理存储源。"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))
