import json
import logging
import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .duckdb_index import clear_index, upsert_image
from .models import ImageryAsset, ImageryDataset, ImageryDatasetMember, ImageryProjectTag, ImageryRecord
from .stac import build_stac_item_from_metadata


logger = logging.getLogger(__name__)


def resolve_asset_path(asset):
    """Resolve a managed or referenced asset within an explicitly allowed root."""
    try:
        candidate = Path(asset.path)
        if not candidate.is_absolute():
            candidate = Path(settings.DATA_DIR) / candidate
        path = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("资产路径无效或文件不存在。") from exc
    roots = [Path(settings.DATA_DIR).resolve()]
    if getattr(asset, "access_mode", None) == ImageryAsset.ACCESS_REFERENCE and asset.storage_object_id:
        from apps.storage_manager.backends import validate_local_root

        roots.append(validate_local_root(asset.storage_object.endpoint.root_uri))
    if not any(path != root and root in path.parents for root in roots):
        # Keep pre-v8 manually registered assets readable during migration. New
        # referenced assets always carry storage_object and are root-checked above.
        if getattr(asset, "access_mode", None) != ImageryAsset.ACCESS_MANAGED or asset.storage_object_id:
            raise ValueError("资产路径不在允许的存储根目录内。")
    return path


def imagery_dataset_max_members():
    return int(getattr(settings, "IMAGERY_DATASET_MAX_MEMBERS", 200))


def ensure_imagery_manager(imagery, user):
    if not imagery.can_manage(user):
        raise PermissionDenied("Only the first uploader or an administrator can manage this imagery.")


def ensure_dataset_manager(dataset, user):
    if not dataset.can_manage(user):
        raise PermissionDenied("Only the dataset creator or an administrator can manage this dataset.")


def _safe_stac_filename(scene_key, image_id):
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", scene_key).strip("._")
    if not filename:
        return str(image_id)
    if filename != scene_key:
        return f"{filename}-{image_id}"
    return filename


def _metadata_from_record(imagery):
    raw_metadata = imagery.raw_metadata or {}
    return {
        "source_name": imagery.source_name,
        "display_name": imagery.display_name,
        "description": imagery.description,
        "is_archived": imagery.is_archived,
        "platform_code": imagery.platform_code,
        "satellite_name": imagery.satellite_name,
        "sensor": imagery.sensor,
        "imaging_mode": imagery.imaging_mode,
        "imaging_mode_detail": imagery.imaging_mode_detail,
        "imaging_mode_raw": raw_metadata.get("imaging_mode_raw"),
        "imaging_mode_code": raw_metadata.get("imaging_mode_code"),
        "polarization": imagery.polarization,
        "polarizations": imagery.polarizations,
        "polarization_raw": raw_metadata.get("polarization_raw"),
        "product_level": imagery.product_level,
        "acquisition_time": imagery.acquisition_time,
        "acquisition_start": imagery.acquisition_start,
        "acquisition_end": imagery.acquisition_end,
        "time_assumption": imagery.time_assumption,
        "orbit_id": imagery.orbit_id,
        "orbit_direction": imagery.orbit_direction,
        "look_side": imagery.look_side,
        "resolution_m": imagery.resolution_m,
        "pixel_spacing_range_m": imagery.pixel_spacing_range_m,
        "pixel_spacing_azimuth_m": imagery.pixel_spacing_azimuth_m,
        "width": imagery.width,
        "height": imagery.height,
        "incidence_angle_near_deg": imagery.incidence_angle_near_deg,
        "incidence_angle_far_deg": imagery.incidence_angle_far_deg,
        "geometry": imagery.geometry,
        "bbox": imagery.bbox,
        "epsg": imagery.epsg,
        "metadata_status": imagery.metadata_status,
        "spatial_status": imagery.spatial_status,
        "cog_status": imagery.cog_status,
        "cog_path": imagery.cog_path,
    }


def regenerate_stac_item(imagery):
    imagery = (
        ImageryRecord.objects.prefetch_related("assets", "project_tags")
        .get(pk=imagery.pk)
    )
    asset_hrefs = {
        asset.role: f"/api/imagery/{imagery.pk}/assets/{asset.role}"
        for asset in imagery.assets.all()
    }
    project_ids = [str(value) for value in imagery.project_tags.values_list("project_id", flat=True)]
    item = build_stac_item_from_metadata(
        scene_key=imagery.stac_id or imagery.scene_key,
        image_id=str(imagery.pk),
        metadata=_metadata_from_record(imagery),
        asset_hrefs=asset_hrefs,
        project_ids=project_ids,
    )
    target = Path(settings.STAC_DIR) / "items" / f"{_safe_stac_filename(imagery.scene_key, imagery.pk)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(item, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    if imagery.stac_path != str(target):
        ImageryRecord.objects.filter(pk=imagery.pk).update(stac_path=str(target))
        imagery.stac_path = str(target)
    return item


def _projection_record(imagery, stac_json):
    assets = {asset.role: asset.path for asset in imagery.assets.all()}
    project_ids = [str(value) for value in imagery.project_tags.values_list("project_id", flat=True)]
    bbox = list(imagery.bbox or [])
    min_lon, min_lat, max_lon, max_lat = (bbox + [None] * 4)[:4]
    center_lon = (min_lon + max_lon) / 2 if min_lon is not None and max_lon is not None else None
    center_lat = (min_lat + max_lat) / 2 if min_lat is not None and max_lat is not None else None
    return {
        "image_id": str(imagery.pk),
        "stac_id": imagery.stac_id,
        "collection_id": "airmap-imagery",
        "scene_key": imagery.scene_key,
        "project_id": project_ids[0] if project_ids else "",
        "project_ids": "|".join(sorted(project_ids)),
        "owner_id": str(imagery.first_uploaded_by_id),
        "job_id": str(imagery.archive_job_id or ""),
        "item_id": "",
        "source_name": imagery.source_name,
        "display_name": imagery.display_name,
        "description": imagery.description,
        "file_path": assets.get(ImageryAsset.ROLE_DATA),
        "raw_path": assets.get(ImageryAsset.ROLE_DATA),
        "preview_path": assets.get(ImageryAsset.ROLE_PREVIEW),
        "thumbnail_path": assets.get(ImageryAsset.ROLE_THUMBNAIL),
        "platform": imagery.platform_code,
        "satellite_name": imagery.satellite_name,
        "sensor": imagery.sensor,
        "imaging_mode": imagery.imaging_mode,
        "imaging_mode_detail": imagery.imaging_mode_detail,
        "product_level": imagery.product_level,
        "polarization": imagery.polarization,
        "polarizations": imagery.polarizations,
        "resolution_m": imagery.resolution_m,
        "pixel_spacing_range_m": imagery.pixel_spacing_range_m,
        "pixel_spacing_azimuth_m": imagery.pixel_spacing_azimuth_m,
        "acquisition_time": imagery.acquisition_time,
        "acquisition_start": imagery.acquisition_start,
        "acquisition_end": imagery.acquisition_end,
        "center_lon": center_lon,
        "center_lat": center_lat,
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "epsg": imagery.epsg,
        "spatial_status": imagery.spatial_status,
        "metadata_status": imagery.metadata_status,
        "preview_status": imagery.preview_status,
        "cog_status": imagery.cog_status,
        "cog_path": imagery.cog_path,
        "footprint_geojson": imagery.geometry,
        "stac_path": imagery.stac_path,
        "status": imagery.status,
        "is_archived": imagery.is_archived,
        "archived_at": imagery.archived_at,
        "archived_by_id": str(imagery.archived_by_id or ""),
        "stac_json": stac_json,
        "created_at": imagery.created_at,
        "updated_at": imagery.updated_at,
    }


def sync_imagery_projection(imagery_or_id):
    image_id = imagery_or_id.pk if isinstance(imagery_or_id, ImageryRecord) else imagery_or_id
    imagery = (
        ImageryRecord.objects.prefetch_related("assets", "project_tags")
        .get(pk=image_id)
    )
    stac_json = regenerate_stac_item(imagery)
    imagery.refresh_from_db(fields=["stac_path"])
    upsert_image(_projection_record(imagery, stac_json))
    return stac_json


def sync_imagery_projection_safely(imagery_or_id):
    try:
        sync_imagery_projection(imagery_or_id)
        return True
    except Exception:
        logger.exception("Failed to synchronize imagery projection for %s", getattr(imagery_or_id, "pk", imagery_or_id))
        return False


def rebuild_imagery_projection():
    clear_index()
    failures = []
    for image_id in ImageryRecord.objects.values_list("pk", flat=True).iterator():
        try:
            sync_imagery_projection(image_id)
        except Exception as exc:
            logger.exception("Failed to rebuild imagery projection for %s", image_id)
            failures.append((str(image_id), str(exc)))
    return failures


def _locked_dataset(dataset):
    return ImageryDataset.objects.select_for_update().get(pk=dataset.pk)


def _require_active(dataset):
    if dataset.status != ImageryDataset.STATUS_ACTIVE:
        raise ValidationError("Archived datasets cannot be modified.")


def _increment_revision(dataset):
    dataset.revision += 1
    dataset.save(update_fields=["revision", "updated_at"])


@transaction.atomic
def add_dataset_members(dataset, user, imagery_ids):
    dataset = _locked_dataset(dataset)
    ensure_dataset_manager(dataset, user)
    _require_active(dataset)
    ids = list(dict.fromkeys(imagery_ids))
    imagery_by_id = {
        str(imagery.pk): imagery
        for imagery in ImageryRecord.objects.filter(pk__in=ids)
    }
    missing = [image_id for image_id in ids if image_id not in imagery_by_id]
    if missing:
        raise ValidationError({"imagery_ids": f"Unknown imagery: {', '.join(missing)}"})
    archived = [image_id for image_id in ids if imagery_by_id[image_id].is_archived]
    if archived:
        raise ValidationError({"imagery_ids": f"Archived imagery cannot be added: {', '.join(archived)}"})
    existing_ids = set(
        ImageryDatasetMember.objects.filter(dataset=dataset, imagery_id__in=ids)
        .values_list("imagery_id", flat=True)
    )
    new_imagery = [imagery_by_id[image_id] for image_id in ids if image_id not in existing_ids]
    current_count = ImageryDatasetMember.objects.filter(dataset=dataset).count()
    if current_count + len(new_imagery) > imagery_dataset_max_members():
        raise ValidationError({"imagery_ids": f"A dataset can contain at most {imagery_dataset_max_members()} imagery records."})
    if not new_imagery:
        return dataset
    new_imagery.sort(
        key=lambda value: (value.acquisition_time is not None, value.acquisition_time or value.created_at),
        reverse=True,
    )
    max_position = ImageryDatasetMember.objects.filter(dataset=dataset).aggregate(value=Max("position"))["value"]
    start = (max_position + 1) if max_position is not None else 0
    ImageryDatasetMember.objects.bulk_create([
        ImageryDatasetMember(dataset=dataset, imagery=imagery, position=start + offset, added_by=user)
        for offset, imagery in enumerate(new_imagery)
    ])
    _increment_revision(dataset)
    return dataset


@transaction.atomic
def remove_dataset_member(dataset, user, image_id):
    dataset = _locked_dataset(dataset)
    ensure_dataset_manager(dataset, user)
    _require_active(dataset)
    deleted, _ = ImageryDatasetMember.objects.filter(dataset=dataset, imagery_id=image_id).delete()
    if not deleted:
        raise ValidationError({"image_id": "This imagery is not a dataset member."})
    _normalize_member_positions(dataset)
    _increment_revision(dataset)
    return dataset


def _normalize_member_positions(dataset, members=None):
    members = list(members or ImageryDatasetMember.objects.filter(dataset=dataset).order_by("position", "id"))
    changed = []
    for position, member in enumerate(members):
        if member.position != position:
            member.position = position
            changed.append(member)
    if changed:
        ImageryDatasetMember.objects.bulk_update(changed, ["position"])
    return members


@transaction.atomic
def order_dataset_members(dataset, user, imagery_ids, enabled_imagery_ids=None):
    dataset = _locked_dataset(dataset)
    ensure_dataset_manager(dataset, user)
    _require_active(dataset)
    members = list(ImageryDatasetMember.objects.select_for_update().filter(dataset=dataset))
    member_by_id = {str(member.imagery_id): member for member in members}
    requested = list(imagery_ids)
    if len(requested) != len(set(requested)) or set(requested) != set(member_by_id):
        raise ValidationError({"imagery_ids": "The order must contain every dataset member exactly once."})
    if enabled_imagery_ids is not None:
        enabled_ids = set(enabled_imagery_ids)
        if not enabled_ids.issubset(member_by_id):
            raise ValidationError({"enabled_imagery_ids": "Enabled imagery must be dataset members."})
    else:
        enabled_ids = None
    changed = []
    for position, image_id in enumerate(requested):
        member = member_by_id[image_id]
        new_enabled = member.enabled if enabled_ids is None else image_id in enabled_ids
        if member.position != position or member.enabled != new_enabled:
            member.position = position
            member.enabled = new_enabled
            changed.append(member)
    if changed:
        ImageryDatasetMember.objects.bulk_update(changed, ["position", "enabled"])
        _increment_revision(dataset)
    return dataset


@transaction.atomic
def refresh_query_dataset(dataset, user):
    from .serializers import ImageryQuerySerializer
    from .duckdb_index import search_images
    dataset = _locked_dataset(dataset)
    ensure_dataset_manager(dataset, user)
    _require_active(dataset)
    if dataset.membership_type != ImageryDataset.MEMBERSHIP_QUERY:
        raise ValidationError("Only query datasets can be refreshed.")
    serializer = ImageryQuerySerializer(data=dataset.query_definition or {})
    serializer.is_valid(raise_exception=True)
    filters = dict(serializer.validated_data)
    filters.pop("page", None)
    filters.pop("page_size", None)
    result = search_images(user=user, filters=filters, page=1, page_size=imagery_dataset_max_members())
    if result["count"] > imagery_dataset_max_members():
        raise ValidationError(f"Query matches more than {imagery_dataset_max_members()} imagery records.")
    ids = [row["image_id"] for row in result["results"]]
    records = {str(item.pk): item for item in ImageryRecord.objects.filter(pk__in=ids, is_archived=False)}
    ids = [image_id for image_id in ids if image_id in records]
    previous = list(
        ImageryDatasetMember.objects.filter(dataset=dataset)
        .order_by("position", "id")
        .values_list("imagery_id", flat=True)
    )
    if previous != ids:
        ImageryDatasetMember.objects.filter(dataset=dataset).delete()
        ImageryDatasetMember.objects.bulk_create([
            ImageryDatasetMember(dataset=dataset, imagery=records[image_id], position=position, added_by=user)
            for position, image_id in enumerate(ids)
        ])
        dataset.revision += 1
    dataset.last_refreshed_at = timezone.now()
    dataset.save(update_fields=["revision", "last_refreshed_at", "updated_at"])
    return dataset


def refresh_on_ingestion_datasets():
    """Refresh opted-in query datasets after a successful ingestion job."""
    datasets = ImageryDataset.objects.filter(
        status=ImageryDataset.STATUS_ACTIVE,
        membership_type=ImageryDataset.MEMBERSHIP_QUERY,
        refresh_mode=ImageryDataset.REFRESH_ON_INGESTION,
    ).select_related("created_by")
    refreshed = 0
    for dataset in datasets:
        try:
            refresh_query_dataset(dataset, dataset.created_by)
            refreshed += 1
        except Exception:
            logger.exception("Unable to refresh dynamic imagery dataset %s after ingestion", dataset.pk)
    return refreshed


@transaction.atomic
def update_dataset_member(dataset, user, image_id, *, enabled=None, move=None):
    dataset = _locked_dataset(dataset)
    ensure_dataset_manager(dataset, user)
    _require_active(dataset)
    members = list(ImageryDatasetMember.objects.select_for_update().filter(dataset=dataset).order_by("position", "id"))
    current_index = next((index for index, member in enumerate(members) if str(member.imagery_id) == str(image_id)), None)
    if current_index is None:
        raise ValidationError({"image_id": "This imagery is not a dataset member."})
    changed = False
    member = members[current_index]
    if enabled is not None and member.enabled != enabled:
        member.enabled = enabled
        changed = True
    target_index = current_index
    if move == "top":
        target_index = 0
    elif move == "up":
        target_index = max(0, current_index - 1)
    elif move == "down":
        target_index = min(len(members) - 1, current_index + 1)
    elif move == "bottom":
        target_index = len(members) - 1
    if target_index != current_index:
        members.pop(current_index)
        members.insert(target_index, member)
        changed = True
    if changed:
        for position, value in enumerate(members):
            value.position = position
        ImageryDatasetMember.objects.bulk_update(members, ["position", "enabled"])
        _increment_revision(dataset)
    return dataset
