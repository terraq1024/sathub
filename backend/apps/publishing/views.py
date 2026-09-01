import uuid
from urllib.request import urlopen
from urllib.error import HTTPError

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.audit_log.services import record_request_event

from .models import ImageryService, ImageryServiceAsset
from .serializers import ImageryServiceCreateSerializer, ImageryServiceSerializer, ImageryServiceUpdateSerializer, ServicePublishJobSerializer
from .services import create_publish_job, service_zoom_range, titiler_tile_url


def _service_queryset():
    return ImageryService.objects.select_related("source_dataset").prefetch_related(
        "service_assets__imagery",
        "source_dataset__members__imagery",
        "publish_jobs",
    )


def _can_manage(user, service):
    return user.is_staff or user.is_superuser or service.created_by_id == user.id


def _snapshot_bbox(service):
    bboxes = [
        relation.imagery.bbox
        for relation in service.service_assets.all()
        if relation.imagery.bbox and len(relation.imagery.bbox) == 4
    ]
    if not bboxes:
        return None
    return [
        min(value[0] for value in bboxes),
        min(value[1] for value in bboxes),
        max(value[2] for value in bboxes),
        max(value[3] for value in bboxes),
    ]


class ImageryServiceListCreateView(APIView):
    def get(self, request):
        services = _service_queryset().exclude(status=ImageryService.STATUS_ARCHIVED)
        return Response(ImageryServiceSerializer(services, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = ImageryServiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        imagery = data.get("imagery")
        dataset = data.get("dataset")
        if dataset and not (request.user.is_staff or request.user.is_superuser or dataset.created_by_id == request.user.id):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        key = f"svc-{uuid.uuid4().hex[:12]}"
        service = ImageryService.objects.create(
            name=data.get("name") or f"{imagery.source_name if imagery else dataset.name} service",
            service_key=key,
            service_type=(
                ImageryService.TYPE_SINGLE_SCENE if imagery
                else ImageryService.TYPE_DATASET_MOSAIC
            ),
            source_dataset=dataset,
            visibility=data["visibility"],
            render_config=data.get("render_config") or {},
            created_by=request.user,
        )
        if imagery:
            ImageryServiceAsset.objects.create(service=service, imagery=imagery)
        service = _service_queryset().get(pk=service.pk)
        record_request_event(request, action="service.created", object_type="imagery_service", object_id=service.service_key, payload={"service_type": service.service_type})
        return Response(ImageryServiceSerializer(service, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ImageryServiceDetailView(APIView):
    def get_object(self, service_key):
        return _service_queryset().get(service_key=service_key)

    def get(self, request, service_key):
        try:
            service = self.get_object(service_key)
        except ImageryService.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ImageryServiceSerializer(service, context={"request": request}).data)

    def patch(self, request, service_key):
        try:
            service = self.get_object(service_key)
        except ImageryService.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _can_manage(request.user, service):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ImageryServiceUpdateSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ImageryServiceSerializer(self.get_object(service_key), context={"request": request}).data)


class PublishServiceView(APIView):
    def post(self, request, service_key):
        try:
            service = ImageryService.objects.get(service_key=service_key)
        except ImageryService.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _can_manage(request.user, service):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        try:
            job = create_publish_job(service, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        record_request_event(request, action="service.publish_requested", object_type="imagery_service", object_id=service.service_key, payload={"job_id": str(job.id), "target_revision": job.target_revision})
        return Response(ServicePublishJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class OfflineServiceView(APIView):
    def post(self, request, service_key):
        try:
            service = ImageryService.objects.get(service_key=service_key)
        except ImageryService.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not _can_manage(request.user, service):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        service.status = ImageryService.STATUS_OFFLINE
        service.unpublished_at = timezone.now()
        service.save(update_fields=["status", "unpublished_at", "updated_at"])
        record_request_event(request, action="service.offline", object_type="imagery_service", object_id=service.service_key)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ServiceJobsView(APIView):
    def get(self, request, service_key):
        try:
            service_jobs = ImageryService.objects.get(service_key=service_key).publish_jobs.all()
        except ImageryService.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ServicePublishJobSerializer(service_jobs, many=True).data)


class ServiceTileJSONView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key):
        try:
            service = _service_queryset().get(
                service_key=service_key,
                status__in=[ImageryService.STATUS_ONLINE, ImageryService.STATUS_DEGRADED],
            )
        except ImageryService.DoesNotExist:
            return Response({"detail": "Service is not online."}, status=status.HTTP_404_NOT_FOUND)
        if service.visibility != ImageryService.VISIBILITY_PUBLIC and not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        bbox = _snapshot_bbox(service)
        minzoom, maxzoom = service_zoom_range(service)
        base_url = request.build_absolute_uri("/").rstrip("/")
        tile_url = f"{base_url}/api/services/{service.service_key}/tiles/{{z}}/{{x}}/{{y}}.png"
        return Response({"tilejson": "3.0.0", "name": service.name, "tiles": [tile_url], "bounds": bbox or [-180, -85, 180, 85], "minzoom": minzoom, "maxzoom": maxzoom})


class ServiceTileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, service_key, z, x, y):
        try:
            service = ImageryService.objects.get(
                service_key=service_key,
                status__in=[ImageryService.STATUS_ONLINE, ImageryService.STATUS_DEGRADED],
            )
        except ImageryService.DoesNotExist:
            return Response({"detail": "Service is not online."}, status=status.HTTP_404_NOT_FOUND)
        if service.visibility != ImageryService.VISIBILITY_PUBLIC and not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            with urlopen(titiler_tile_url(service, z, x, y), timeout=30) as upstream:
                return HttpResponse(upstream.read(), content_type=upstream.headers.get_content_type(), status=upstream.status)
        except HTTPError as exc:
            if exc.code == 404:
                return HttpResponse(status=204)
            return Response({"detail": f"TiTiler returned HTTP {exc.code}."}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            return Response({"detail": f"TiTiler request failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
