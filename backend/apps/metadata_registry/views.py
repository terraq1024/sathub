from pathlib import Path

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.imagery.metadata import ProductGroup
from apps.imagery.models import ImageryRecord

from .engine import run_parser
from .models import MetadataOverride, MetadataQualityIssue, MetadataSchema, ParserRun, ParserTemplate, ParserTemplateVersion
from .permissions import RegistryReadAdminWritePermission, RegistryReadOnlyPermission
from .serializers import DryRunSerializer, MetadataOverrideSerializer, MetadataQualityIssueSerializer, MetadataSchemaSerializer, ParserRunSerializer, ParserTemplateSerializer, ParserTemplateVersionSerializer


def _group_for_imagery(imagery):
    files = {asset.role: Path(asset.path) for asset in imagery.assets.all()}
    grouped = {}
    for role, path in files.items():
        if role == "data":
            grouped[path.suffix.lower()] = path
        elif role == "preview":
            grouped["preview.jpg"] = path
        elif role == "thumbnail":
            grouped["thumbnail.jpg"] = path
        elif role == "metadata":
            grouped["meta.xml"] = path
        elif role == "incidence":
            grouped["incidence.xml"] = path
        elif role == "log":
            grouped["log"] = path
    return ProductGroup(stem=imagery.scene_key, files=grouped)


class SchemaListCreateView(generics.ListCreateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    queryset = MetadataSchema.objects.prefetch_related("fields")
    serializer_class = MetadataSchemaSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SchemaDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    queryset = MetadataSchema.objects.prefetch_related("fields")
    serializer_class = MetadataSchemaSerializer


class TemplateListCreateView(generics.ListCreateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    queryset = ParserTemplate.objects.select_related("schema")
    serializer_class = ParserTemplateSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class TemplateDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    queryset = ParserTemplate.objects.select_related("schema")
    serializer_class = ParserTemplateSerializer


class TemplateVersionListCreateView(generics.ListCreateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    serializer_class = ParserTemplateVersionSerializer

    def get_queryset(self):
        return ParserTemplateVersion.objects.filter(template_id=self.kwargs["template_id"]).select_related("template")

    def perform_create(self, serializer):
        serializer.save(template_id=self.kwargs["template_id"], created_by=self.request.user)


class TemplateVersionPublishView(APIView):
    permission_classes = [RegistryReadAdminWritePermission]
    def post(self, request, version_id):
        version = get_object_or_404(ParserTemplateVersion.objects.select_related("template", "template__schema"), pk=version_id)
        if version.status == ParserTemplateVersion.STATUS_PUBLISHED:
            return Response(ParserTemplateVersionSerializer(version).data)
        version.status = ParserTemplateVersion.STATUS_PUBLISHED
        version.published_by = request.user
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_by", "published_at"])
        version.template.status = ParserTemplate.STATUS_ACTIVE
        version.template.save(update_fields=["status", "updated_at"])
        if version.template.schema.status == MetadataSchema.STATUS_DRAFT:
            version.template.schema.status = MetadataSchema.STATUS_ACTIVE
            version.template.schema.save(update_fields=["status", "updated_at"])
        return Response(ParserTemplateVersionSerializer(version).data)


class ParserRunListView(generics.ListAPIView):
    permission_classes = [RegistryReadOnlyPermission]
    queryset = ParserRun.objects.select_related("parser_version", "imagery")
    serializer_class = ParserRunSerializer


class ParserRunDetailView(generics.RetrieveAPIView):
    permission_classes = [RegistryReadOnlyPermission]
    queryset = ParserRun.objects.select_related("parser_version", "imagery")
    serializer_class = ParserRunSerializer


class QualityIssueListView(generics.ListAPIView):
    permission_classes = [RegistryReadOnlyPermission]
    serializer_class = MetadataQualityIssueSerializer

    def get_queryset(self):
        queryset = MetadataQualityIssue.objects.select_related("imagery", "parser_run")
        params = self.request.query_params
        imagery_id = params.get("imagery_id")
        if imagery_id:
            queryset = queryset.filter(imagery_id=imagery_id)
        status_value = params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        severity = params.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)
        return queryset


class OverrideListCreateView(generics.ListCreateAPIView):
    permission_classes = [RegistryReadAdminWritePermission]
    serializer_class = MetadataOverrideSerializer

    def get_queryset(self):
        queryset = MetadataOverride.objects.select_related("imagery", "created_by")
        imagery_id = self.request.query_params.get("imagery_id")
        return queryset.filter(imagery_id=imagery_id) if imagery_id else queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class DryRunView(APIView):
    permission_classes = [RegistryReadOnlyPermission]
    def post(self, request):
        serializer = DryRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        imagery = get_object_or_404(ImageryRecord.objects.prefetch_related("assets"), pk=serializer.validated_data["imagery_id"])
        version = None
        if serializer.validated_data.get("parser_version_id"):
            version = get_object_or_404(ParserTemplateVersion, pk=serializer.validated_data["parser_version_id"])
        _, parsed = run_parser(_group_for_imagery(imagery), imagery=imagery, parser_version=version, dry_run=True)
        return Response(parsed)


class ExtractionRunCreateView(APIView):
    permission_classes = [RegistryReadAdminWritePermission]
    def post(self, request):
        serializer = DryRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        imagery = get_object_or_404(ImageryRecord.objects.prefetch_related("assets"), pk=serializer.validated_data["imagery_id"])
        version = get_object_or_404(ParserTemplateVersion, pk=serializer.validated_data["parser_version_id"]) if serializer.validated_data.get("parser_version_id") else None
        run, parsed = run_parser(_group_for_imagery(imagery), imagery=imagery, parser_version=version, user=request.user)
        return Response(ParserRunSerializer(run).data if run else parsed, status=status.HTTP_201_CREATED)
