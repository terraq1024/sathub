from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    AdminPasswordResetSerializer,
    PasswordSerializer,
    RegisterSerializer,
    UserAdminSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


def _feature_flags():
    def has_app(label):
        return f"apps.{label}" in settings.INSTALLED_APPS

    return {
        "services": has_app("publishing"),
        "processing": has_app("processing"),
        "delivery": has_app("delivery"),
        "storage_manager": has_app("storage_manager"),
        "metadata_registry": has_app("metadata_registry"),
        "catalog_governance": has_app("catalog_governance"),
        "audit_log": has_app("audit_log"),
        "token_auth": has_app("access_control"),
    }


class CapabilitiesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        features = _feature_flags()
        return Response({
            "edition": "enterprise" if features["services"] else "oss",
            "features": features,
        })


class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        # Check the account before authenticate: authenticate folds disabled
        # accounts into the same "invalid credentials" error, which would
        # mislead a re-activated-on-paper user.
        try:
            account = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            account = None
        if account is not None and not account.is_active:
            return Response({"detail": "账号已被停用。"}, status=status.HTTP_403_FORBIDDEN)
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RegisterView(APIView):
    """Open registration: anyone can create a regular account."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = PasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        # Passwords set by an admin may be unusable; only verify a current
        # password when the account has one.
        if user.has_usable_password() and not user.check_password(serializer.validated_data["current_password"]):
            return Response({"detail": "当前密码不正确。"}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)
        return Response({"detail": "密码已更新。"})


class IsStaffPermission(permissions.BasePermission):
    message = "只有管理员可以管理用户。"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class UserListView(APIView):
    permission_classes = [IsStaffPermission]

    def get(self, request):
        queryset = User.objects.all().order_by("-date_joined")
        return Response(UserAdminSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserAdminSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [IsStaffPermission]

    def patch(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        serializer = UserUpdateSerializer(target, data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        update_fields = []
        if "email" in data:
            target.email = data["email"]
            update_fields.append("email")
        if "is_staff" in data:
            if target.pk == request.user.pk and not data["is_staff"]:
                return Response({"detail": "不能撤销自己的管理员权限。"}, status=status.HTTP_400_BAD_REQUEST)
            target.is_staff = data["is_staff"]
            update_fields.append("is_staff")
        if "is_active" in data:
            if target.pk == request.user.pk and not data["is_active"]:
                return Response({"detail": "不能停用自己的账号。"}, status=status.HTTP_400_BAD_REQUEST)
            target.is_active = data["is_active"]
            update_fields.append("is_active")
        if update_fields:
            target.save(update_fields=update_fields)
        return Response(UserAdminSerializer(target).data)

    def delete(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        if target.pk == request.user.pk:
            return Response({"detail": "不能删除自己的账号。"}, status=status.HTTP_400_BAD_REQUEST)
        if target.is_superuser and not request.user.is_superuser:
            return Response({"detail": "无权删除超级管理员。"}, status=status.HTTP_403_FORBIDDEN)
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminPasswordResetView(APIView):
    permission_classes = [IsStaffPermission]

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        serializer = AdminPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.set_password(serializer.validated_data["new_password"])
        target.save(update_fields=["password"])
        return Response({"detail": "密码已重置。"})
