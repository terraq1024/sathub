from pathlib import Path

from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.services import accessible_projects_for

try:
    from apps.audit_log.services import record_request_event
except ImportError:  # OSS edition bundles without the audit app
    def record_request_event(*args, **kwargs):
        return None

from rest_framework.exceptions import ValidationError as DRFValidationError

from .models import IngestionItem, IngestionJob
from .serializers import ArchiveCheckSerializer, FolderUploadSerializer, IngestionItemSerializer, IngestionJobSerializer, UrlImportSerializer, ZipUploadSerializer
from .services import create_archive_upload_job, create_folder_upload_job, create_url_import_job, find_existing_archive, retry_item


class UrlImportView(APIView):
    def post(self, request):
        serializer = UrlImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job = create_url_import_job(
                user=request.user,
                project_id=serializer.validated_data.get("project_id"),
                urls=serializer.validated_data["urls"],
            )
        except ValueError as exc:
            raise DRFValidationError(str(exc)) from exc
        record_request_event(request, action="ingestion.created", object_type="ingestion_job", object_id=job.id, payload={"source_type": job.source_type, "count": job.total_count})
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class ZipUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ZipUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        archive_filename = Path(serializer.validated_data["file"].name).name
        existing = find_existing_archive(archive_filename)
        if existing:
            return Response(
                {
                    "detail": "Archive already exists.",
                    "filename": archive_filename,
                    "image_id": existing.id,
                    "source_name": existing.source_name,
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            job = create_archive_upload_job(
                user=request.user,
                project_id=serializer.validated_data.get("project_id"),
                uploaded_file=serializer.validated_data["file"],
            )
        except ValueError as exc:
            raise DRFValidationError(str(exc)) from exc
        record_request_event(request, action="ingestion.created", object_type="ingestion_job", object_id=job.id, payload={"source_type": job.source_type, "filename": archive_filename})
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class ArchiveCheckView(APIView):
    def get(self, request):
        serializer = ArchiveCheckSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filename = serializer.validated_data["filename"]
        existing = find_existing_archive(filename)
        return Response({
            "exists": existing is not None,
            "filename": filename,
            "image_id": existing.id if existing else None,
            "source_name": existing.source_name if existing else None,
        })


class FolderUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = FolderUploadSerializer(data={
            "project_id": request.data.get("project_id"),
            "files": request.FILES.getlist("files"),
            "relative_paths": request.data.getlist("relative_paths"),
        })
        serializer.is_valid(raise_exception=True)
        try:
            job = create_folder_upload_job(
                user=request.user,
                project_id=serializer.validated_data.get("project_id"),
                files=serializer.validated_data["files"],
                relative_paths=serializer.validated_data["relative_paths"],
            )
        except ValueError as exc:
            raise DRFValidationError(str(exc)) from exc
        record_request_event(request, action="ingestion.created", object_type="ingestion_job", object_id=job.id, payload={"source_type": job.source_type, "file_count": len(serializer.validated_data["files"])})
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class IngestionJobListView(generics.ListAPIView):
    serializer_class = IngestionJobSerializer

    def get_queryset(self):
        queryset = IngestionJob.objects.select_related("project", "created_by")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(created_by=self.request.user)


class IngestionJobDetailView(generics.RetrieveAPIView):
    serializer_class = IngestionJobSerializer
    lookup_url_kwarg = "job_id"

    def get_queryset(self):
        queryset = IngestionJob.objects.select_related("project", "created_by")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(created_by=self.request.user)


class IngestionJobItemsView(generics.ListAPIView):
    serializer_class = IngestionItemSerializer

    def get_queryset(self):
        queryset = IngestionItem.objects.filter(job_id=self.kwargs["job_id"])
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(job__created_by=self.request.user)


class IngestionItemRetryView(APIView):
    def post(self, request, item_id):
        filters = {"id": item_id}
        if not (request.user.is_staff or request.user.is_superuser):
            filters["job__created_by"] = request.user
        try:
            item = IngestionItem.objects.get(**filters)
        except IngestionItem.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        item = retry_item(item)
        record_request_event(request, action="ingestion.item_retried", object_type="ingestion_item", object_id=item.id, payload={"job_id": item.job_id})
        return Response(IngestionItemSerializer(item).data)
