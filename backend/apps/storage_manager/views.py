from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StorageEndpoint, StorageObject, StorageScanJob
from .backends import StorageBackendError
from .permissions import IsStorageUser
from .serializers import StorageEndpointSerializer, StorageObjectSerializer, StorageScanJobSerializer, StorageReferenceIngestionSerializer
from .services import create_reference_ingestion_job, create_scan_job


def _visible_endpoint_or_404(endpoint_id, user):
    from django.shortcuts import get_object_or_404

    endpoint = get_object_or_404(StorageEndpoint, pk=endpoint_id)
    if not (user.is_staff or user.is_superuser or str(endpoint.created_by_id) == str(user.pk)):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("只有存储源的创建者和管理员可以访问。")
    return endpoint


class EndpointListCreateView(APIView):
    permission_classes = [IsStorageUser]

    def get(self, request):
        queryset = StorageEndpoint.objects.all()
        if not (request.user.is_staff or request.user.is_superuser):
            queryset = queryset.filter(created_by=request.user)
        return Response(StorageEndpointSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = StorageEndpointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save(created_by=request.user)
        # Registering a directory is the whole point: scan it right away so
        # the discovered scenes flow into the catalog automatically (the scan
        # triggers reference ingestion for every new group on completion).
        try:
            create_scan_job(endpoint=endpoint, user=request.user, mode=StorageScanJob.MODE_FULL)
        except (ValueError, StorageBackendError) as exc:
            # The endpoint exists but its first scan failed; surface the reason
            # without failing the registration itself.
            endpoint.status = StorageEndpoint.STATUS_ERROR
            endpoint.status_message = str(exc)
            endpoint.save(update_fields=["status", "status_message", "updated_at"])
        return Response(StorageEndpointSerializer(endpoint).data, status=status.HTTP_201_CREATED)


class EndpointDetailView(APIView):
    permission_classes = [IsStorageUser]

    def get_object(self, endpoint_id):
        return _visible_endpoint_or_404(endpoint_id, self.request.user)

    def get(self, request, endpoint_id):
        return Response(StorageEndpointSerializer(self.get_object(endpoint_id)).data)

    def patch(self, request, endpoint_id):
        endpoint = self.get_object(endpoint_id)
        serializer = StorageEndpointSerializer(endpoint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save()
        return Response(StorageEndpointSerializer(endpoint).data)

    def delete(self, request, endpoint_id):
        endpoint = self.get_object(endpoint_id)
        endpoint.enabled = False
        endpoint.save(update_fields=["enabled", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EndpointCheckView(APIView):
    permission_classes = [IsStorageUser]

    def post(self, request, endpoint_id):
        endpoint = _visible_endpoint_or_404(endpoint_id, request.user)
        try:
            job = create_scan_job(endpoint=endpoint, user=request.user, mode=StorageScanJob.MODE_HEALTH_CHECK)
        except (ValueError, PermissionError, StorageBackendError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StorageScanJobSerializer(job).data, status=status.HTTP_200_OK if job.status == StorageScanJob.STATUS_SUCCEEDED else status.HTTP_400_BAD_REQUEST)


class EndpointScanView(APIView):
    permission_classes = [IsStorageUser]

    def post(self, request, endpoint_id):
        endpoint = _visible_endpoint_or_404(endpoint_id, request.user)
        mode = request.data.get("mode", StorageScanJob.MODE_INCREMENTAL)
        prefix = request.data.get("prefix", "")
        try:
            job = create_scan_job(endpoint=endpoint, user=request.user, mode=mode, prefix=prefix)
        except (ValueError, PermissionError, StorageBackendError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StorageScanJobSerializer(job).data, status=status.HTTP_201_CREATED if job.status != StorageScanJob.STATUS_FAILED else status.HTTP_400_BAD_REQUEST)


class EndpointIngestView(APIView):
    permission_classes = [IsStorageUser]

    def post(self, request, endpoint_id):
        endpoint = _visible_endpoint_or_404(endpoint_id, request.user)
        serializer = StorageReferenceIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            from apps.ingestion.serializers import IngestionJobSerializer

            job = create_reference_ingestion_job(
                endpoint=endpoint,
                user=request.user,
                object_ids=serializer.validated_data["object_ids"],
                project_id=serializer.validated_data.get("project_id"),
                visibility=request.data.get("visibility", "private"),
            )
        except (ValueError, PermissionError, StorageBackendError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class ScanJobListView(APIView):
    permission_classes = [IsStorageUser]

    def get(self, request):
        queryset = StorageScanJob.objects.select_related("endpoint", "created_by")
        if not (request.user.is_staff or request.user.is_superuser):
            queryset = queryset.filter(endpoint__created_by=request.user)
        endpoint_id = request.query_params.get("endpoint")
        if endpoint_id:
            queryset = queryset.filter(endpoint_id=endpoint_id)
        return Response(StorageScanJobSerializer(queryset[:200], many=True).data)


class ScanJobDetailView(APIView):
    permission_classes = [IsStorageUser]

    def get(self, request, job_id):
        job = get_object_or_404(StorageScanJob.objects.select_related("endpoint", "created_by"), pk=job_id)
        return Response(StorageScanJobSerializer(job).data)


class ObjectListView(APIView):
    permission_classes = [IsStorageUser]

    def get(self, request):
        queryset = StorageObject.objects.select_related("endpoint", "last_seen_scan")
        if not (request.user.is_staff or request.user.is_superuser):
            queryset = queryset.filter(endpoint__created_by=request.user)
        if request.query_params.get("endpoint"):
            queryset = queryset.filter(endpoint_id=request.query_params["endpoint"])
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("scene_stem"):
            queryset = queryset.filter(scene_stem__icontains=request.query_params["scene_stem"])
        return Response(StorageObjectSerializer(queryset[:500], many=True).data)


class ObjectDetailView(APIView):
    permission_classes = [IsStorageUser]

    def get(self, request, object_id):
        obj = get_object_or_404(StorageObject.objects.select_related("endpoint", "last_seen_scan"), pk=object_id)
        return Response(StorageObjectSerializer(obj).data)
