from rest_framework.permissions import BasePermission


class RegistryReadAdminWritePermission(BasePermission):
    """Authenticated users may inspect registry state; staff may change it."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return bool(request.user.is_staff or request.user.is_superuser)


class RegistryReadOnlyPermission(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

