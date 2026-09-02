from pathlib import Path
import hashlib
import json
import os
import subprocess
from math import atan2, degrees as _degrees

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

try:
    from apps.audit_log.services import record_request_event
except ImportError:  # OSS edition bundles without the audit app
    def record_request_event(*args, **kwargs):
        return None

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .duckdb_index import get_image, imagery_facets, search_images
from .models import ImageryAsset, ImageryDataset, ImageryDatasetMember, ImageryProjectTag, ImageryRecord, ImagerySavedSearch
from .serializers import (
    DatasetMemberAddSerializer,
    DatasetMemberOrderSerializer,
    DatasetMemberUpdateSerializer,
    ImageryBatchSerializer,
    ImageryDatasetDetailSerializer,
    ImageryDatasetSerializer,
    ImageryDatasetWriteSerializer,
    ImageryQuerySerializer,
    ImageryRecordSerializer,
    ImageryUpdateSerializer,
    ImagerySavedSearchSerializer,
)
from .services import (
    add_dataset_members,
    ensure_dataset_manager,
    ensure_imagery_manager,
    order_dataset_members,
    remove_dataset_member,
    sync_imagery_projection_safely,
    update_dataset_member,
    refresh_query_dataset,
    remove_imagery,
    resolve_asset_path,
)


TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_true(value):
    return str(value).lower() in TRUE_VALUES


def _governance_image_ids(filters):
    governance_keys = ("administrative_unit_id", "classification_id", "tag_id")
    if not any(filters.get(key) for key in governance_keys):
        return None
    try:
        from apps.catalog_governance.services import imagery_ids_for_filters
    except ImportError:  # OSS edition bundles without catalog governance
        return []

    def values(key):
        raw = filters.get(key) or ""
        return [value.strip() for value in str(raw).split(",") if value.strip()]

    ids = imagery_ids_for_filters(
        administrative_unit_ids=values("administrative_unit_id"),
        classification_ids=values("classification_id"),
        tag_ids=values("tag_id"),
        include_archived=bool(filters.get("include_archived")),
    )
    return list(ids[:10000])


def _dataset_queryset():
    member_queryset = (
        ImageryDatasetMember.objects.select_related("imagery", "added_by")
        .prefetch_related("imagery__assets")
        .order_by("position", "id")
    )
    return (
        ImageryDataset.objects.select_related("created_by")
        .prefetch_related(Prefetch("members", queryset=member_queryset))
    )


def _visible_dataset_or_404(request, dataset_id, include_archived=False):
    queryset = _dataset_queryset()
    if include_archived:
        if not request.user.is_staff:
            queryset = queryset.filter(Q(status=ImageryDataset.STATUS_ACTIVE) | Q(created_by=request.user))
    else:
        queryset = queryset.filter(status=ImageryDataset.STATUS_ACTIVE)
    return get_object_or_404(queryset, pk=dataset_id)


def _dataset_response(request, dataset_id, *, detail=True, response_status=status.HTTP_200_OK):
    dataset = get_object_or_404(_dataset_queryset(), pk=dataset_id)
    serializer_class = ImageryDatasetDetailSerializer if detail else ImageryDatasetSerializer
    return Response(serializer_class(dataset, context={"request": request}).data, status=response_status)


class ImageryListView(APIView):
    def get(self, request):
        serializer = ImageryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        page = data.pop("page")
        page_size = data.pop("page_size")
        ids = _governance_image_ids(data)
        if ids is not None:
            data["image_ids"] = ids
        result = search_images(user=request.user, filters=data, page=page, page_size=page_size)
        return Response(result)


class ImageryFacetsView(APIView):
    def get(self, request):
        return Response(imagery_facets(user=request.user))


class ImageryDetailView(APIView):
    def get(self, request, image_id):
        image = get_image(
            user=request.user,
            image_id=image_id,
            include_archived=_is_true(request.query_params.get("include_archived")),
        )
        if image is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(image)

    def patch(self, request, image_id):
        serializer = ImageryUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            imagery = get_object_or_404(ImageryRecord.objects.select_for_update(), pk=image_id)
            ensure_imagery_manager(imagery, request.user)
            if imagery.is_archived:
                raise ValidationError("Restore archived imagery before editing it.")
            data = serializer.validated_data
            update_fields = []
            for field in ("display_name", "description"):
                if field in data:
                    setattr(imagery, field, data[field])
                    update_fields.append(field)
            if update_fields:
                imagery.save(update_fields=[*update_fields, "updated_at"])
            if "project_ids" in data:
                desired = set(data["project_ids"])
                ImageryProjectTag.objects.filter(imagery=imagery).exclude(project_id__in=desired).delete()
                existing = set(imagery.project_tags.values_list("project_id", flat=True))
                ImageryProjectTag.objects.bulk_create([
                    ImageryProjectTag(imagery=imagery, project_id=project_id)
                    for project_id in desired - existing
                ])
        synced = sync_imagery_projection_safely(image_id)
        record_request_event(request, action="imagery.updated", object_type="imagery", object_id=image_id, payload={"fields": update_fields, "projection_synced": synced})
        imagery = ImageryRecord.objects.select_related("first_uploaded_by", "archived_by").prefetch_related("project_tags").get(pk=image_id)
        response = Response(ImageryRecordSerializer(imagery, context={"request": request}).data)
        response["X-Imagery-Projection-Synced"] = str(synced).lower()
        return response

    def delete(self, request, image_id):
        changed = False
        with transaction.atomic():
            imagery = get_object_or_404(ImageryRecord.objects.select_for_update(), pk=image_id)
            ensure_imagery_manager(imagery, request.user)
            if not imagery.is_archived:
                imagery.is_archived = True
                imagery.archived_at = timezone.now()
                imagery.archived_by = request.user
                imagery.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
                changed = True
        if changed:
            sync_imagery_projection_safely(image_id)
            record_request_event(request, action="imagery.archived", object_type="imagery", object_id=image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ImageryRemoveView(APIView):
    """Hard-remove an imagery record from catalog, index and (for managed
    assets) the platform data directory.

    Referenced assets (directory ingestion) are never deleted from their
    storage endpoint — only the catalog entry goes.
    """

    def delete(self, request, image_id):
        with transaction.atomic():
            imagery = get_object_or_404(ImageryRecord.objects.select_for_update(), pk=image_id)
            ensure_imagery_manager(imagery, request.user)
            modes = {asset.role: getattr(asset, "access_mode", None) for asset in imagery.assets.all()}
            has_managed = any(mode == ImageryAsset.ACCESS_MANAGED for mode in modes.values())
            has_referenced = any(mode == ImageryAsset.ACCESS_REFERENCE for mode in modes.values())
            remove_imagery(imagery, delete_files=True)
        record_request_event(request, action="imagery.removed", object_type="imagery", object_id=image_id, payload={"had_managed_assets": has_managed})
        return Response({"removed": image_id, "referenced_assets_kept": has_referenced}, status=status.HTTP_200_OK)


class ImageryRestoreView(APIView):
    def post(self, request, image_id):
        changed = False
        with transaction.atomic():
            imagery = get_object_or_404(ImageryRecord.objects.select_for_update(), pk=image_id)
            ensure_imagery_manager(imagery, request.user)
            if imagery.is_archived:
                imagery.is_archived = False
                imagery.archived_at = None
                imagery.archived_by = None
                imagery.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])
                changed = True
        synced = sync_imagery_projection_safely(image_id) if changed else True
        if changed:
            record_request_event(request, action="imagery.restored", object_type="imagery", object_id=image_id, payload={"projection_synced": synced})
        imagery = ImageryRecord.objects.select_related("first_uploaded_by", "archived_by").prefetch_related("project_tags").get(pk=image_id)
        response = Response(ImageryRecordSerializer(imagery, context={"request": request}).data)
        response["X-Imagery-Projection-Synced"] = str(synced).lower()
        return response


class ImageryBatchView(APIView):
    def post(self, request):
        serializer = ImageryBatchSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        image_ids = data["imagery_ids"]
        with transaction.atomic():
            records = list(ImageryRecord.objects.select_for_update().filter(pk__in=image_ids))
            record_by_id = {str(record.pk): record for record in records}
            missing = [image_id for image_id in image_ids if image_id not in record_by_id]
            if missing:
                raise ValidationError({"imagery_ids": f"Unknown imagery: {', '.join(missing)}"})
            for record in records:
                ensure_imagery_manager(record, request.user)
            action = data["action"]
            now = timezone.now()
            if action == ImageryBatchSerializer.ACTION_ARCHIVE:
                ImageryRecord.objects.filter(pk__in=image_ids).update(
                    is_archived=True,
                    archived_at=now,
                    archived_by=request.user,
                    updated_at=now,
                )
            elif action == ImageryBatchSerializer.ACTION_RESTORE:
                ImageryRecord.objects.filter(pk__in=image_ids).update(
                    is_archived=False,
                    archived_at=None,
                    archived_by=None,
                    updated_at=now,
                )
            elif action == ImageryBatchSerializer.ACTION_ADD_PROJECT:
                ImageryProjectTag.objects.bulk_create([
                    ImageryProjectTag(imagery=record, project_id=data["project_id"])
                    for record in records
                ], ignore_conflicts=True)
            else:
                ImageryProjectTag.objects.filter(imagery_id__in=image_ids, project_id=data["project_id"]).delete()
        failed_sync_ids = [image_id for image_id in image_ids if not sync_imagery_projection_safely(image_id)]
        record_request_event(request, action=f"imagery.batch_{data['action']}", object_type="imagery_batch", payload={"imagery_ids": image_ids, "projection_failed_ids": failed_sync_ids})
        return Response({
            "action": data["action"],
            "count": len(image_ids),
            "projection_synced": not failed_sync_ids,
            "projection_failed_ids": failed_sync_ids,
        })


class ImageryStacView(APIView):
    def get(self, request, image_id):
        image = get_image(
            user=request.user,
            image_id=image_id,
            include_archived=_is_true(request.query_params.get("include_archived")),
        )
        if image is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(image.get("stac_json") or {})


def _tiff_rotation_degrees(source: Path) -> float | None:
    """Return the raster's affine rotation in degrees, or None when unknown.

    Vendor GEC products (Umbra spotlight in particular) carry rotated
    north-east-up affines: an axis-aligned Leaflet overlay would shear them,
    so the preview must be warped upright before display.
    """
    try:
        import tifffile

        with tifffile.TiffFile(str(source)) as tif:
            page = tif.pages[0]
            tag = page.tags.get("ModelTransformationTag")
            if tag is None:
                return 0.0
            values = tag.value  # flat 16-tuple; a b c d / e f g h / ...
            a, b = float(values[0]), float(values[1])
            scale = (abs(a) + abs(b)) or 1.0
            return abs(_degrees(atan2(b, a))) if abs(b) / scale > 1e-6 else 0.0
    except Exception:
        return None


def _warp_north_up(source: Path, cache_dir: Path) -> tuple[Path, list[float]] | None:
    """Warp a rotated raster to an axis-aligned EPSG:4326 preview.

    Runs in whatever interpreter the warp runtime locates (an isolated
    rasterio venv when configured, otherwise the current interpreter if it
    can import rasterio). Returns (jpeg_path, 4326 bounds) so the overlay
    can be placed exactly.
    """
    from .warp_runtime import run_warp_payload

    script = Path(__file__).with_name("preview_warper.py")
    payload = run_warp_payload(script, {"source": str(source), "max_size": 2400})
    if payload is None or not payload.get("ok"):
        return None
    try:
        import base64

        import numpy as np
        from PIL import Image

        array = np.frombuffer(base64.b64decode(payload["array_b64"]), dtype="float32")
        array = array.reshape(payload["height"], payload["width"])
        finite = array[np.isfinite(array)]
        if not finite.size:
            return None
        low, high = np.percentile(finite, [2, 98])
        normalized = np.clip((array - low) * 255 / max(high - low, 1), 0, 255).astype("uint8")
        target = cache_dir / f"warp-{hashlib.sha1(str(source).encode()).hexdigest()[:12]}-{int(source.stat().st_mtime_ns)}.jpg"
        Image.fromarray(normalized, mode="L").save(target, format="JPEG", quality=90, optimize=True)
        return target, payload["bounds"]
    except Exception:
        return None


def _serve_preview_as_jpeg(asset, source: Path):
    """Transcode a TIFF quick-look to a cached JPEG the browser can display.

    Cached under the derived-asset root keyed by source path + mtime, so the
    multi-hundred-MB Capella preview is converted only once per revision.
    Giga-pixel previews are read from their pyramid overview page instead of
    being decoded at full size. Rotated rasters are warped north-up first and
    the caller receives the corrected 4326 bounds alongside the JPEG path.
    """
    cache_dir = Path(settings.DERIVED_PREVIEW_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{source}|{source.stat().st_mtime_ns}".encode()).hexdigest()[:16]
    target = cache_dir / f"{asset.imagery_id}-{asset.role}-{digest}.jpg"
    warped_bounds = None
    rotation = _tiff_rotation_degrees(source)
    if rotation is not None and rotation > 0.5:
        warped = _warp_north_up(source, cache_dir)
        if warped:
            target, warped_bounds = warped
            return target, warped_bounds
    if target.is_file():
        return target, warped_bounds
    try:
        import numpy as np
        import tifffile
        from PIL import Image

        with tifffile.TiffFile(str(source)) as tif:
            pages = list(tif.pages)
            if not pages:
                return None, None
            # Pick the smallest page still larger than the target preview box
            # (pyramid overviews), so huge rasters stay cheap to decode.
            page = pages[0]
            for candidate in pages[1:]:
                if max(candidate.shape[:2]) >= 2400:
                    page = candidate
                else:
                    break
            array = np.asarray(page.asarray())
        if np.iscomplexobj(array):
            array = np.abs(array)
        if array.ndim > 2:
            array = array[0] if array.shape[0] <= 4 else array[..., 0]
        if array.ndim != 2 or not array.size:
            return None, None
        image = Image.fromarray(array)
        if image.mode not in ("L", "RGB"):
            image = image.convert("L")
        image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        image.save(target, format="JPEG", quality=90, optimize=True)
        return target, warped_bounds
    except Exception:
        pass
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        with Image.open(source) as image:
            if image.mode not in ("L", "RGB"):
                image = image.convert("L")
            image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            image.save(target, format="JPEG", quality=90, optimize=True)
        return target, warped_bounds
    except Exception:
        return None, None


def _stored_preview_warp_bounds(imagery) -> list[float] | None:
    """Read sathub:preview_warp_bounds off the record's STAC properties.

    Ingest stores the corrected extent when the generated preview is a
    north-up warp of a rotated raster.
    """
    try:
        item = None
        if imagery.stac_path:
            item = json.loads(Path(imagery.stac_path).read_text(encoding="utf-8"))
        if not isinstance(item, dict):
            return None
        bounds = (item.get("properties") or {}).get("sathub:preview_warp_bounds")
        if isinstance(bounds, list) and len(bounds) == 4 and all(isinstance(v, (int, float)) for v in bounds):
            return [float(v) for v in bounds]
    except (OSError, ValueError, TypeError):
        pass
    return None


class ImageryAssetView(APIView):
    def get(self, request, image_id, role):
        return self._serve(request, image_id, role)

    def head(self, request, image_id, role):
        # Browsers probe rotated-raster previews with HEAD to read the
        # X-Imagery-Preview-Bounds alignment header before overlaying.
        # DRF's default HEAD->GET mapping also covers this, but keeping an
        # explicit handler guarantees the header on both methods.
        return self._serve(request, image_id, role)

    def _serve(self, request, image_id, role):
        try:
            asset = ImageryAsset.objects.select_related("imagery").get(
                imagery_id=image_id,
                imagery__is_archived=False,
                role=role,
            )
        except ImageryAsset.DoesNotExist:
            return Response({"detail": "Asset not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            path = resolve_asset_path(asset)
        except (ValueError, OSError):
            return Response({"detail": "Asset file is missing."}, status=status.HTTP_404_NOT_FOUND)
        # Vendor quick-looks (ICEYE QLK / Capella preview) are TIFF rasters
        # that browsers cannot render in <img>; serve them transcoded to JPEG.
        # Rotated rasters (Umbra spotlight GEC) come back north-up warped with
        # corrected bounds, which the overlay then uses instead of the bbox.
        if role in ("preview", "thumbnail") and path.suffix.lower() in (".tif", ".tiff"):
            converted = _serve_preview_as_jpeg(asset, path)
            if converted:
                converted_path, corrected_bounds = converted
                response = FileResponse(converted_path.open("rb"), content_type="image/jpeg")
                response["Content-Length"] = str(converted_path.stat().st_size)
                response["Cache-Control"] = "public, max-age=86400"
                if corrected_bounds:
                    response["X-Imagery-Preview-Bounds"] = ",".join(f"{value:.7f}" for value in corrected_bounds)
                return response
        try:
            response = FileResponse(path.open("rb"), content_type=asset.media_type or "application/octet-stream")
            response["Content-Length"] = str(path.stat().st_size)
        except OSError:
            return Response({"detail": "Asset file is missing."}, status=status.HTTP_404_NOT_FOUND)
        # Ingest-generated previews of rotated rasters are already warped
        # north-up JPEGs; their corrected extent is stored on the record's
        # STAC properties and surfaces through the same alignment header.
        if role == "preview":
            warp_bounds = _stored_preview_warp_bounds(asset.imagery)
            if warp_bounds:
                response["X-Imagery-Preview-Bounds"] = ",".join(f"{value:.7f}" for value in warp_bounds)
        return response


class ImageryMapView(APIView):
    def get(self, request):
        serializer = ImageryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        filters.pop("page", None)
        filters.pop("page_size", None)
        filters["include_archived"] = False
        ids = _governance_image_ids(filters)
        if ids is not None:
            filters["image_ids"] = ids
        result = search_images(user=request.user, filters=filters, page=1, page_size=200)
        features = []
        for image in result["results"]:
            geometry = image.get("geometry")
            if not geometry:
                continue
            properties = {
                key: image.get(key)
                for key in [
                    "image_id", "scene_key", "source_name", "display_name", "effective_display_name",
                    "platform", "satellite_name", "sensor", "imaging_mode", "polarization", "product_level",
                    "resolution_m", "acquisition_time", "preview_status", "min_lon", "min_lat", "max_lon", "max_lat",
                ]
            }
            properties["preview_url"] = f"/api/imagery/{image['image_id']}/assets/preview"
            features.append({"type": "Feature", "id": image["image_id"], "geometry": geometry, "properties": properties})
        return Response({"type": "FeatureCollection", "features": features, "count": result["count"]})


class ImageryDatasetListCreateView(APIView):
    def get(self, request):
        include_archived = _is_true(request.query_params.get("include_archived"))
        queryset = _dataset_queryset()
        if include_archived:
            if not request.user.is_staff:
                queryset = queryset.filter(Q(status=ImageryDataset.STATUS_ACTIVE) | Q(created_by=request.user))
        else:
            queryset = queryset.filter(status=ImageryDataset.STATUS_ACTIVE)
        search = (request.query_params.get("q") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(200, int(request.query_params.get("page_size", 200))))
        except (TypeError, ValueError):
            page_size = 200
        total = queryset.count()
        offset = (page - 1) * page_size
        page_items = list(queryset[offset:offset + page_size])
        return Response({
            "count": total,
            "results": ImageryDatasetSerializer(page_items, many=True, context={"request": request}).data,
        })

    def post(self, request):
        serializer = ImageryDatasetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        imagery_ids = data.pop("imagery_ids", [])
        with transaction.atomic():
            dataset = ImageryDataset.objects.create(created_by=request.user, **data)
            if imagery_ids:
                add_dataset_members(dataset, request.user, imagery_ids)
        record_request_event(request, action="dataset.created", object_type="imagery_dataset", object_id=dataset.pk, payload={"member_count": len(imagery_ids)})
        return _dataset_response(request, dataset.pk, response_status=status.HTTP_201_CREATED)


class ImageryDatasetDetailView(APIView):
    def get(self, request, dataset_id):
        dataset = _visible_dataset_or_404(
            request,
            dataset_id,
            include_archived=_is_true(request.query_params.get("include_archived")),
        )
        return Response(ImageryDatasetDetailSerializer(dataset, context={"request": request}).data)

    def patch(self, request, dataset_id):
        with transaction.atomic():
            dataset = get_object_or_404(ImageryDataset.objects.select_for_update(), pk=dataset_id)
            ensure_dataset_manager(dataset, request.user)
            if dataset.status != ImageryDataset.STATUS_ACTIVE:
                raise ValidationError("Archived datasets cannot be modified.")
            serializer = ImageryDatasetWriteSerializer(dataset, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            if "imagery_ids" in serializer.validated_data:
                raise ValidationError({"imagery_ids": "Use the dataset members endpoint to modify members."})
            if not serializer.validated_data:
                raise ValidationError("At least one editable field is required.")
            serializer.save()
        record_request_event(request, action="dataset.updated", object_type="imagery_dataset", object_id=dataset.pk)
        return _dataset_response(request, dataset.pk)

    def delete(self, request, dataset_id):
        with transaction.atomic():
            dataset = get_object_or_404(ImageryDataset.objects.select_for_update(), pk=dataset_id)
            ensure_dataset_manager(dataset, request.user)
            if dataset.status != ImageryDataset.STATUS_ARCHIVED:
                dataset.status = ImageryDataset.STATUS_ARCHIVED
                dataset.archived_at = timezone.now()
                dataset.save(update_fields=["status", "archived_at", "updated_at"])
                record_request_event(request, action="dataset.archived", object_type="imagery_dataset", object_id=dataset.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ImageryDatasetMemberListView(APIView):
    def post(self, request, dataset_id):
        dataset = get_object_or_404(ImageryDataset, pk=dataset_id)
        serializer = DatasetMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        add_dataset_members(dataset, request.user, serializer.validated_data["imagery_ids"])
        return _dataset_response(request, dataset.pk)


class ImageryDatasetRefreshView(APIView):
    def post(self, request, dataset_id):
        dataset = get_object_or_404(ImageryDataset, pk=dataset_id)
        refresh_query_dataset(dataset, request.user)
        return _dataset_response(request, dataset.pk)


class ImagerySavedSearchListCreateView(APIView):
    def get(self, request):
        queryset = ImagerySavedSearch.objects.select_related("created_by")
        if not request.user.is_staff:
            queryset = queryset.filter(created_by=request.user)
        return Response(ImagerySavedSearchSerializer(queryset, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = ImagerySavedSearchSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        search = serializer.save(created_by=request.user)
        return Response(ImagerySavedSearchSerializer(search, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ImagerySavedSearchDetailView(APIView):
    def _managed(self, request, search_id):
        search = get_object_or_404(ImagerySavedSearch, pk=search_id)
        if not search.can_manage(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only the creator or an administrator can manage this saved search.")
        return search

    def patch(self, request, search_id):
        search = self._managed(request, search_id)
        serializer = ImagerySavedSearchSerializer(search, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        search = serializer.save()
        return Response(ImagerySavedSearchSerializer(search, context={"request": request}).data)

    def delete(self, request, search_id):
        self._managed(request, search_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ImageryDatasetMemberDetailView(APIView):
    def patch(self, request, dataset_id, image_id):
        dataset = get_object_or_404(ImageryDataset, pk=dataset_id)
        serializer = DatasetMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_dataset_member(dataset, request.user, image_id, **serializer.validated_data)
        return _dataset_response(request, dataset.pk)

    def delete(self, request, dataset_id, image_id):
        dataset = get_object_or_404(ImageryDataset, pk=dataset_id)
        remove_dataset_member(dataset, request.user, image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ImageryDatasetMemberOrderView(APIView):
    def put(self, request, dataset_id):
        dataset = get_object_or_404(ImageryDataset, pk=dataset_id)
        serializer = DatasetMemberOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_dataset_members(
            dataset,
            request.user,
            serializer.validated_data["imagery_ids"],
            serializer.validated_data.get("enabled_imagery_ids"),
        )
        return _dataset_response(request, dataset.pk)
