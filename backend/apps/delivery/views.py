from django.http import FileResponse
from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.imagery.models import ImageryRecord
from apps.imagery.serializers import ImageryRecordSerializer
from apps.audit_log.services import record_request_event
from .models import DeliveryBasket, DeliveryBasketItem, DeliverySnapshot, ExportJob
from .serializers import DeliverySnapshotCreateSerializer, DeliverySnapshotSerializer, ExportCreateSerializer, ExportJobSerializer, ImageryIdsSerializer
from .services import basket_for, create_delivery_snapshot, create_export


class BasketView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        basket = basket_for(request.user)
        items = list(basket.items.select_related("imagery").prefetch_related("imagery__project_tags"))
        return Response({
            "id": basket.id,
            "imagery_ids": [item.imagery_id for item in items],
            "items": [{
                "id": item.id,
                "imagery_id": item.imagery_id,
                "imagery": ImageryRecordSerializer(item.imagery, context={"request": request}).data,
                "added_at": item.added_at,
            } for item in items],
            "count": len(items),
        })
    def _add(self, request):
        data = ImageryIdsSerializer(data=request.data); data.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(data.validated_data["imagery_ids"]))
        existing = set(ImageryRecord.objects.filter(id__in=ids, is_archived=False).values_list("id", flat=True))
        if len(existing) != len(ids): return Response({"detail": "存在不存在或已归档的影像"}, status=400)
        basket = basket_for(request.user)
        for image_id in ids: DeliveryBasketItem.objects.get_or_create(basket=basket, imagery_id=image_id)
        return self.get(request)
    def delete(self, request):
        basket_for(request.user).items.all().delete(); return self.get(request)

    def post(self, request, *args, **kwargs):
        if request.path.rstrip("/").endswith("/clear"):
            basket_for(request.user).items.all().delete()
            return self.get(request)
        return self._add(request)


class BasketItemView(APIView):
    permission_classes = [IsAuthenticated]
    def delete(self, request, image_id):
        deleted, _ = basket_for(request.user).items.filter(imagery_id=image_id).delete()
        return Response(status=204 if deleted else 404)


class ExportListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request): return Response(ExportJobSerializer(ExportJob.objects.filter(owner=request.user).order_by("-created_at"), many=True).data)
    def post(self, request):
        data = ExportCreateSerializer(data=request.data); data.is_valid(raise_exception=True)
        try: job = create_export(request, request.user, data.validated_data["format"], list(basket_for(request.user).items.values_list("imagery_id", flat=True)))
        except ValueError as exc: return Response({"detail": str(exc)}, status=400)
        record_request_event(request, action="delivery.export_requested", object_type="export_job", object_id=job.id, payload={"format": job.format})
        return Response(ExportJobSerializer(job).data, status=202)


class SnapshotListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = DeliverySnapshot.objects.select_related("owner")
        if not request.user.is_staff:
            queryset = queryset.filter(owner=request.user)
        return Response(DeliverySnapshotSerializer(queryset[:200], many=True).data)

    def post(self, request):
        serializer = DeliverySnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = basket_for(request.user).items.filter(imagery__is_archived=False).values_list("imagery_id", flat=True)
        try:
            snapshot = create_delivery_snapshot(owner=request.user, imagery_ids=list(ids), **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        record_request_event(request, action="delivery.snapshot_frozen", object_type="delivery_snapshot", object_id=snapshot.id, payload={"imagery_count": len(snapshot.imagery_ids)})
        return Response(DeliverySnapshotSerializer(snapshot).data, status=201)


class SnapshotDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, snapshot_id):
        queryset = DeliverySnapshot.objects.select_related("owner")
        if not request.user.is_staff:
            queryset = queryset.filter(owner=request.user)
        snapshot = get_object_or_404(queryset, pk=snapshot_id)
        return Response(DeliverySnapshotSerializer(snapshot).data)

    def post(self, request, snapshot_id):
        snapshot = get_object_or_404(DeliverySnapshot, pk=snapshot_id)
        if snapshot.owner_id != request.user.id and not request.user.is_staff:
            return Response(status=404)
        serializer = ExportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            from .services import _validate_images
            _validate_images(snapshot.imagery_ids)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        job = ExportJob.objects.create(owner=request.user, format=serializer.validated_data["format"], imagery_ids=snapshot.imagery_ids, snapshot=snapshot, expires_at=timezone.now() + timedelta(days=1))
        record_request_event(request, action="delivery.snapshot_export_requested", object_type="delivery_snapshot", object_id=snapshot.id, payload={"job_id": str(job.id), "format": job.format})
        return Response(ExportJobSerializer(job).data, status=202)


class ExportDetailView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, job_id):
        try: job = ExportJob.objects.get(id=job_id)
        except ExportJob.DoesNotExist: return Response(status=404)
        if job.owner_id != request.user.id and not request.user.is_staff: return Response(status=404)
        return Response(ExportJobSerializer(job).data)


class DownloadView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, job_id):
        try: job = ExportJob.objects.get(id=job_id)
        except ExportJob.DoesNotExist: return Response(status=404)
        if job.owner_id != request.user.id and not request.user.is_staff: return Response(status=404)
        if job.status != ExportJob.STATUS_DONE or not job.file_path or (job.expires_at and job.expires_at < timezone.now()): return Response({"detail": "文件尚未生成或已过期"}, status=404)
        if not Path(job.file_path).is_file():
            return Response({"detail": "导出文件不存在"}, status=404)
        filename = f"airmap-{job.id}.json" if job.format in (ExportJob.FORMAT_MANIFEST, ExportJob.FORMAT_STAC) else f"airmap-{job.id}.zip"
        record_request_event(request, action="delivery.downloaded", object_type="export_job", object_id=job.id, payload={"format": job.format})
        return FileResponse(open(job.file_path, "rb"), as_attachment=True, filename=filename)
