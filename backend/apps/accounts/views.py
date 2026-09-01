from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


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
