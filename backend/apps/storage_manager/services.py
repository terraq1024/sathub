from __future__ import annotations

import os
import re
from pathlib import PurePosixPath

from django.db import transaction
from django.utils import timezone

from .backends import get_backend, validate_local_root, validate_prefix
from .models import StorageEndpoint, StorageObject, StorageScanJob

ROLE_SUFFIXES = (
    (".meta.incidence.xml", StorageObject.ROLE_INCIDENCE),
    (".meta.xml", StorageObject.ROLE_METADATA),
    ("_extended.json.json", StorageObject.ROLE_METADATA),
    (".json", StorageObject.ROLE_METADATA),
    (".result.xml", StorageObject.ROLE_RESULT),
    (".thumb.jpeg", StorageObject.ROLE_THUMBNAIL),
    (".thumb.jpg", StorageObject.ROLE_THUMBNAIL),
    ("_thumb.png", StorageObject.ROLE_THUMBNAIL),
    (".jpeg", StorageObject.ROLE_PREVIEW),
    (".jpg", StorageObject.ROLE_PREVIEW),
    ("_preview.tif", StorageObject.ROLE_PREVIEW),
    ("_preview.tiff", StorageObject.ROLE_PREVIEW),
    ("_qlk.tif", StorageObject.ROLE_PREVIEW),
    ("_qlk.tiff", StorageObject.ROLE_PREVIEW),
    ("_qlk.png", StorageObject.ROLE_PREVIEW),
    (".tiff", StorageObject.ROLE_DATA),
    (".tif", StorageObject.ROLE_DATA),
    (".jp2", StorageObject.ROLE_DATA),
    (".log", StorageObject.ROLE_LOG),
)


def scene_parts(object_key):
    path = PurePosixPath(object_key)
    filename = path.name
    lowered = filename.lower()
    role = StorageObject.ROLE_OTHER
    stem = path.stem
    for suffix, candidate_role in ROLE_SUFFIXES:
        if lowered.endswith(suffix):
            role = candidate_role
            stem = filename[:-len(suffix)]
            break
    if lowered.endswith("_extended.json.json"):
        stem = filename[:-len("_extended.json.json")]
    elif lowered.endswith(".stac.v2.json"):
        stem = filename[:-len(".stac.v2.json")]
    # Vendors publish one scene as a directory of product-specific files
    # (``_GEC.tif``, ``_SLC.json``, ``_extended.json``, ...). Strip those
    # product suffixes so every file lands in the same scene group.
    stem = re.sub(
        r"_(?:GEC|GEO|CSI(?:_MM)?|SICD(?:_MM)?|SIDD(?:_MM)?|CPHD|MM"
        r"|GRD|SLC|QLK|THM|METADATA|EXTENDED|PREVIEW|THUMB"
        r"|SHP|KML|PNG|CPHD(?:_MM)?)$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    # Capella quick-look assets come from the sibling GEO product line while
    # the primary data is GEC; normalize GEO -> GEC so they share one group.
    stem = re.sub(r"_GEO_", "_GEC_", stem, count=1, flags=re.IGNORECASE)
    parent = str(path.parent)
    group = f"{parent}/{stem}" if parent != "." else stem
    return stem, group, role


def _scope_filter(queryset, prefix):
    if prefix:
        return queryset.filter(object_key__startswith=f"{prefix}/") | queryset.filter(object_key=prefix)
    return queryset


def create_scan_job(*, endpoint, user, mode=StorageScanJob.MODE_INCREMENTAL, prefix=""):
    if not user.is_staff and not user.is_superuser:
        raise PermissionError("只有管理员可以扫描存储源。")
    if not endpoint.enabled:
        raise ValueError("存储源已禁用，不能发起扫描。")
    prefix = validate_prefix(prefix)
    if mode not in {StorageScanJob.MODE_FULL, StorageScanJob.MODE_INCREMENTAL, StorageScanJob.MODE_HEALTH_CHECK}:
        raise ValueError("不支持的扫描模式。")
    job = StorageScanJob.objects.create(endpoint=endpoint, mode=mode, prefix=prefix, created_by=user)
    return run_scan(job)


def create_reference_ingestion_job(*, endpoint, user, object_ids, project_id=None):
    """Create an ingestion job that reads product groups in-place from a local/NAS endpoint."""
    if not user.is_staff and not user.is_superuser:
        raise PermissionError("只有管理员可以从存储源登记影像。")
    from apps.ingestion.models import IngestionItem, IngestionJob
    from apps.ingestion.services import get_project_for_user

    objects = list(
        StorageObject.objects.filter(endpoint=endpoint, id__in=list(dict.fromkeys(object_ids)))
        .order_by("scene_group_key", "object_key")
    )
    if not objects:
        raise ValueError("没有找到可登记的存储对象。")
    if any(obj.missing_confirmed for obj in objects):
        raise ValueError("选择中包含已确认缺失的文件。")
    groups = sorted({obj.scene_group_key for obj in objects if obj.scene_group_key})
    data_groups = set(
        StorageObject.objects.filter(endpoint=endpoint, scene_group_key__in=groups, scene_role=StorageObject.ROLE_DATA)
        .values_list("scene_group_key", flat=True)
    )
    metadata_groups = set(
        StorageObject.objects.filter(endpoint=endpoint, scene_group_key__in=groups, scene_role=StorageObject.ROLE_METADATA)
        .values_list("scene_group_key", flat=True)
    )
    groups = [group for group in groups if group in data_groups or group in metadata_groups]
    if not groups:
        raise ValueError("选择中没有包含可识别的影像数据或 STAC 元数据。")
    project = get_project_for_user(user, project_id)
    job = IngestionJob.objects.create(
        created_by=user,
        project=project,
        source_type=IngestionJob.SOURCE_STORAGE_REFERENCE,
        total_count=len(groups),
        source_payload={"storage_endpoint_id": str(endpoint.pk), "storage_object_ids": [str(obj.pk) for obj in objects]},
    )
    root = validate_local_root(endpoint.root_uri)
    children = []
    for group in groups:
        # scene_group_key uses "/" separators; Windows roots need native backslashes
        # while POSIX roots accept the forward-slash form as-is.
        group_path = root / group.replace("/", "\\") if os.name == "nt" else root / group
        children.append(IngestionItem(
            job=job,
            source=group_path.name,
            source_kind=IngestionItem.SOURCE_FILE,
            raw_path=str(group_path.parent),
            relative_path=group,
        ))
    IngestionItem.objects.bulk_create(children)
    return job


def _mark_missing(job, seen_keys):
    queryset = _scope_filter(StorageObject.objects.filter(endpoint=job.endpoint), job.prefix)
    count = 0
    for obj in queryset.exclude(object_key__in=seen_keys).iterator():
        obj.status = StorageObject.STATUS_MISSING
        obj.missing_scan_count += 1
        obj.missing_confirmed = obj.missing_scan_count >= 2
        obj.last_seen_scan = job
        obj.save(update_fields=["status", "missing_scan_count", "missing_confirmed", "last_seen_scan"])
        count += 1
    return count


@transaction.atomic
def run_scan(job):
    job.status = StorageScanJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "started_at", "error_message"])
    endpoint = job.endpoint
    try:
        backend = get_backend(endpoint)
        backend.check()
        endpoint.status = StorageEndpoint.STATUS_ONLINE
        endpoint.status_message = ""
        endpoint.last_check_at = timezone.now()
        endpoint.save(update_fields=["status", "status_message", "last_check_at", "updated_at"])
        if job.mode == StorageScanJob.MODE_HEALTH_CHECK:
            job.status = StorageScanJob.STATUS_SUCCEEDED
            job.finished_at = timezone.now()
            job.checkpoint = {"phase": "health_check", "completed": True}
            job.save(update_fields=["status", "finished_at", "checkpoint"])
            return job
        seen = set()
        group_keys = set()
        for entry in backend.iter_objects(job.prefix):
            seen.add(entry.object_key)
            stem, group_key, role = scene_parts(entry.object_key)
            group_keys.add(group_key)
            obj = StorageObject.objects.filter(endpoint=endpoint, object_key=entry.object_key).first()
            if obj is None:
                obj = StorageObject(endpoint=endpoint, object_key=entry.object_key, scene_stem=stem, scene_group_key=group_key, scene_role=role)
                obj.status = StorageObject.STATUS_NEW
                job.new_count += 1
            elif obj.fingerprint == entry.fingerprint and obj.size_bytes == entry.size_bytes:
                obj.status = StorageObject.STATUS_UNCHANGED
                job.unchanged_count += 1
            else:
                obj.status = StorageObject.STATUS_CHANGED
                job.changed_count += 1
            obj.scene_stem = stem
            obj.scene_group_key = group_key
            obj.scene_role = role
            obj.size_bytes = entry.size_bytes
            obj.modified_at = entry.modified_at
            obj.fingerprint = entry.fingerprint
            obj.missing_scan_count = 0
            obj.missing_confirmed = False
            obj.last_seen_at = timezone.now()
            obj.last_verified_at = timezone.now()
            obj.last_seen_scan = job
            obj.source_metadata = {"relative_path": entry.object_key, "backend": "local_directory"}
            obj.save()
            job.files_scanned += 1
            job.checkpoint = {"phase": "scanning", "last_object_key": entry.object_key, "files_scanned": job.files_scanned}
            job.save(update_fields=["files_scanned", "checkpoint", "new_count", "changed_count", "unchanged_count"])
        job.missing_count = _mark_missing(job, seen)
        job.scenes_found = len(group_keys)
        job.status = StorageScanJob.STATUS_SUCCEEDED
        job.finished_at = timezone.now()
        job.checkpoint = {"phase": "completed", "last_object_key": max(seen) if seen else "", "files_scanned": job.files_scanned, "completed_at": job.finished_at.isoformat()}
        job.save(update_fields=["missing_count", "scenes_found", "status", "finished_at", "checkpoint"])
        endpoint.last_scan_at = job.finished_at
        endpoint.save(update_fields=["last_scan_at", "updated_at"])
        return job
    except Exception as exc:
        job.status = StorageScanJob.STATUS_FAILED
        job.finished_at = timezone.now()
        job.error_message = str(exc)[:4000]
        job.checkpoint = {**job.checkpoint, "phase": "failed", "error": job.error_message}
        job.save(update_fields=["status", "finished_at", "error_message", "checkpoint"])
        endpoint.status = StorageEndpoint.STATUS_ERROR
        endpoint.status_message = job.error_message
        endpoint.last_check_at = timezone.now()
        endpoint.save(update_fields=["status", "status_message", "last_check_at", "updated_at"])
        return job
