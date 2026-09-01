from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AdministrativeUnit, Classification, Tag
from .serializers import (
    AdministrativeTreeSerializer,
    AdministrativeUnitSerializer,
    AssociationWriteSerializer,
    ClassificationSerializer,
    ClassificationWriteSerializer,
    ImageryAdministrativeUnitSerializer,
    ImageryClassificationSerializer,
    ImageryIdsQuerySerializer,
    ImageryTagSerializer,
    TagSerializer,
)
from .services import imagery_ids_for_filters, link_datasets, link_imagery


class StaffWriteMixin:
    def check_write(self, request):
        if not request.user.is_staff:
            return Response({"detail": "只有管理员可以维护目录分类和标签。"}, status=status.HTTP_403_FORBIDDEN)
        return None


class AdministrativeUnitTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = AdministrativeUnit.objects.filter(is_valid=True, parent__isnull=True)
        source_version = request.query_params.get("source_version")
        if source_version:
            queryset = queryset.filter(source_version=source_version)
        return Response(AdministrativeTreeSerializer(queryset, many=True).data)


class AdministrativeUnitListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = AdministrativeUnit.objects.filter(is_valid=True)
        for field in ("level", "code", "source_version"):
            if request.query_params.get(field):
                queryset = queryset.filter(**{field: request.query_params[field]})
        if request.query_params.get("parent_id"):
            queryset = queryset.filter(parent_id=request.query_params["parent_id"])
        return Response(AdministrativeUnitSerializer(queryset, many=True).data)


class ClassificationListCreateView(StaffWriteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Classification.objects.all()
        if request.query_params.get("enabled") is not None:
            queryset = queryset.filter(enabled=request.query_params["enabled"].lower() in {"1", "true", "yes"})
        return Response(ClassificationSerializer(queryset, many=True).data)

    def post(self, request):
        denied = self.check_write(request)
        if denied:
            return denied
        serializer = ClassificationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            classification = serializer.save(created_by=request.user)
        except IntegrityError:
            return Response({"detail": "同级分类名称已存在。"}, status=status.HTTP_409_CONFLICT)
        return Response(ClassificationSerializer(classification).data, status=status.HTTP_201_CREATED)


class ClassificationDetailView(StaffWriteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, classification_id):
        return Response(ClassificationSerializer(get_object_or_404(Classification, pk=classification_id)).data)

    def patch(self, request, classification_id):
        denied = self.check_write(request)
        if denied:
            return denied
        classification = get_object_or_404(Classification, pk=classification_id)
        serializer = ClassificationWriteSerializer(classification, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            classification = serializer.save()
        except IntegrityError:
            return Response({"detail": "同级分类名称已存在。"}, status=status.HTTP_409_CONFLICT)
        return Response(ClassificationSerializer(classification).data)

    def delete(self, request, classification_id):
        denied = self.check_write(request)
        if denied:
            return denied
        classification = get_object_or_404(Classification, pk=classification_id)
        classification.enabled = False
        classification.save(update_fields=["enabled", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TagListCreateView(StaffWriteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Tag.objects.all()
        if request.query_params.get("enabled") is not None:
            queryset = queryset.filter(enabled=request.query_params["enabled"].lower() in {"1", "true", "yes"})
        return Response(TagSerializer(queryset, many=True).data)

    def post(self, request):
        denied = self.check_write(request)
        if denied:
            return denied
        serializer = TagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tag = serializer.save(created_by=request.user)
        except IntegrityError:
            return Response({"detail": "标签名称已存在。"}, status=status.HTTP_409_CONFLICT)
        return Response(TagSerializer(tag).data, status=status.HTTP_201_CREATED)


class TagDetailView(StaffWriteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, tag_id):
        return Response(TagSerializer(get_object_or_404(Tag, pk=tag_id)).data)

    def patch(self, request, tag_id):
        denied = self.check_write(request)
        if denied:
            return denied
        tag = get_object_or_404(Tag, pk=tag_id)
        serializer = TagSerializer(tag, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            tag = serializer.save()
        except IntegrityError:
            return Response({"detail": "标签名称已存在。"}, status=status.HTTP_409_CONFLICT)
        return Response(TagSerializer(tag).data)

    def delete(self, request, tag_id):
        denied = self.check_write(request)
        if denied:
            return denied
        tag = get_object_or_404(Tag, pk=tag_id)
        tag.enabled = False
        tag.save(update_fields=["enabled", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssociationView(StaffWriteMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        denied = self.check_write(request)
        if denied:
            return denied
        serializer = AssociationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                if data["object_type"] == "imagery":
                    link_imagery(imagery_ids=data["object_ids"], user=request.user, **{key: data[key] for key in ("classification_ids", "tag_ids", "replace")})
                else:
                    link_datasets(dataset_ids=data["object_ids"], user=request.user, **{key: data[key] for key in ("classification_ids", "tag_ids", "replace")})
        except (ValueError, IntegrityError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"linked": True, "object_type": data["object_type"], "object_ids": data["object_ids"]})


class ImageryIdsQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_data = request.query_params.copy()
        for field in ("administrative_unit_ids", "classification_ids", "tag_ids"):
            values = request.query_params.getlist(field)
            if len(values) == 1:
                values = [item.strip() for item in values[0].split(",") if item.strip()]
            if values:
                query_data.setlist(field, values)
        serializer = ImageryIdsQuerySerializer(data=query_data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ids = imagery_ids_for_filters(**data)
        return Response({"imagery_ids": list(ids)})


class ImageryGovernanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, imagery_id):
        from apps.imagery.models import ImageryRecord

        imagery = get_object_or_404(ImageryRecord, pk=imagery_id)
        return Response({
            "imagery_id": imagery_id,
            "administrative_units": ImageryAdministrativeUnitSerializer(
                imagery.administrative_units.select_related("administrative_unit"), many=True
            ).data,
            "classifications": ImageryClassificationSerializer(
                imagery.classifications.select_related("classification"), many=True
            ).data,
            "tags": ImageryTagSerializer(
                imagery.catalog_tags.select_related("tag"), many=True
            ).data,
        })
