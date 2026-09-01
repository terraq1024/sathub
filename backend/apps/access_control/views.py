from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.imagery.models import ImageryAsset, ImageryRecord
from apps.imagery.services import resolve_asset_path

from .authentication import BearerTokenAuthentication, has_scope
from .models import ApiAccessToken
from .range_response import ranged_file_response
from .serializers import AssetSignSerializer, ApiAccessTokenSerializer, TokenCreateSerializer
from .signing import build_signed_path, valid_signature


class SessionOnly(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and isinstance(request.successful_authenticator, SessionAuthentication)


class TokenListCreateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [SessionOnly]

    def get(self, request):
        return Response(ApiAccessTokenSerializer(ApiAccessToken.objects.filter(user=request.user), many=True).data)

    def post(self, request):
        serializer = TokenCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token, raw = ApiAccessToken.issue(user=request.user, **serializer.validated_data)
        result = ApiAccessTokenSerializer(token).data
        result["token"] = raw
        return Response(result, status=status.HTTP_201_CREATED)


class TokenRevokeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [SessionOnly]

    def delete(self, request, token_id):
        token = ApiAccessToken.objects.filter(pk=token_id, user=request.user).first()
        if not token:
            raise NotFound()
        if not token.revoked_at:
            token.revoked_at = timezone.now()
            token.save(update_fields=["revoked_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SignAssetView(APIView):
    authentication_classes = [SessionAuthentication, BearerTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.successful_authenticator and isinstance(request.successful_authenticator, BearerTokenAuthentication) and not has_scope(request.auth, "assets/read"):
            raise PermissionDenied("Missing assets/read scope")
        serializer = AssetSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["role"] not in {choice[0] for choice in ImageryAsset.ROLE_CHOICES}:
            return Response({"detail": "Invalid asset role"}, status=400)
        imagery = ImageryRecord.objects.filter(pk=data["image_id"], is_archived=False).first()
        if not imagery:
            raise NotFound()
        if not ImageryAsset.objects.filter(imagery=imagery, role=data["role"]).exists():
            raise NotFound()
        expiry = int((timezone.now() + timedelta(seconds=data["expires_in"])).timestamp())
        return Response({"url": build_signed_path(request, imagery.pk, data["role"], expiry), "expires": expiry})


def _safe_asset_path(asset):
    try:
        return resolve_asset_path(asset)
    except ValueError as exc:
        raise PermissionDenied("Invalid asset path") from exc


class SignedAssetView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def _serve(self, request, image_id, role):
        try:
            expiry = int(request.query_params.get("expires", ""))
        except ValueError:
            return Response(status=403)
        if expiry < int(timezone.now().timestamp()) or not valid_signature(image_id, role, expiry, request.query_params.get("signature")):
            return Response(status=403)
        if role not in {choice[0] for choice in ImageryAsset.ROLE_CHOICES}:
            raise NotFound()
        asset = ImageryAsset.objects.filter(imagery_id=image_id, imagery__is_archived=False, role=role).first()
        if not asset:
            raise NotFound()
        return ranged_file_response(request, _safe_asset_path(asset), asset.media_type or "application/octet-stream")

    def get(self, request, image_id, role):
        return self._serve(request, image_id, role)

    def head(self, request, image_id, role):
        return self._serve(request, image_id, role)
