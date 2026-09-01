import json
import os
import tempfile
import zipfile
import re
import hashlib
import mimetypes
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.imagery.models import ImageryAsset, ImageryRecord
from apps.imagery.services import resolve_asset_path
from apps.access_control.signing import build_signed_path
from apps.imagery.stac import build_stac_item_from_metadata
from .models import DeliveryBasket, DeliverySnapshot, ExportJob


MAX_ITEMS = getattr(settings, "DELIVERY_MAX_ITEMS", 200)


def basket_for(user):
    basket, _ = DeliveryBasket.objects.get_or_create(owner=user)
    return basket


def asset_url(request, image_id, role="data", expires=None):
    if expires:
        return build_signed_path(request, image_id, role, expires)
    return request.build_absolute_uri(f"/api/imagery/{image_id}/assets/{role}")


def _metadata(image):
    return {field: getattr(image, field) for field in (
        "scene_key", "source_name", "display_name", "description", "platform_code", "satellite_name", "sensor",
        "imaging_mode", "imaging_mode_detail", "polarization", "polarizations", "product_level", "acquisition_time",
        "acquisition_start", "acquisition_end", "resolution_m", "pixel_spacing_range_m", "pixel_spacing_azimuth_m",
        "width", "height", "geometry", "bbox", "epsg", "metadata_status", "spatial_status", "preview_status",
    )}


def _json_default(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def safe_archive_basename(value, suffix=".bin"):
    """Return a single safe ZIP member name, never a path."""
    name = Path(str(value).replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = name.replace("..", "_").strip(" .")
    if not name or name in {".", ".."}:
        name = "imagery"
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    stem = Path(name).stem or "imagery"
    return f"{stem[:180]}{suffix.lower()}"


def safe_archive_component(value, fallback="scene"):
    """Return one bounded ZIP path component with no traversal semantics."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).replace("\\", "/").split("/")[-1])
    name = name.replace("..", "_").strip(" .")
    return (name or fallback)[:180]


def file_sha256(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_media_type(asset):
    return asset.media_type or mimetypes.guess_type(asset.name or "")[0] or "application/octet-stream"


def asset_details(request, image, expires=None):
    details = []
    for asset in image.assets.all():
        try:
            path = resolve_asset_path(asset)
        except ValueError:
            continue
        details.append({
            "role": asset.role,
            "name": asset.name,
            "media_type": asset_media_type(asset),
            "size_bytes": path.stat().st_size,
            "checksum_sha256": asset.checksum_sha256 or file_sha256(path),
            "url": asset_url(request, image.id, asset.role, expires),
        })
    return details


def build_records(request, images, expires=None):
    records = []
    for image in images:
        assets = {}
        for asset in image.assets.all():
            try:
                resolve_asset_path(asset)
            except ValueError:
                continue
            assets[asset.role] = asset
        records.append({"id": image.id, "scene_key": image.scene_key, "metadata": _metadata(image),
                        # Keep the original role -> URL map for existing clients.
                        "assets": {role: asset_url(request, image.id, role, expires) for role in assets},
                        "asset_details": asset_details(request, image, expires)})
    return records


def _validate_images(ids):
    images = list(ImageryRecord.objects.prefetch_related("assets").filter(id__in=ids))
    by_id = {x.id: x for x in images}
    if len(images) != len(set(ids)):
        raise ValueError("影像不存在或已被删除")
    for image in images:
        if image.is_archived:
            raise ValueError(f"影像已归档: {image.scene_key}")
        data = image.assets.filter(role=ImageryAsset.ROLE_DATA).first()
        if not data or not data.path:
            raise ValueError(f"主数据资产缺失: {image.scene_key}")
        try:
            resolve_asset_path(data)
        except ValueError as exc:
            raise ValueError(f"主数据资产缺失: {image.scene_key}") from exc
    return [by_id[x] for x in ids]


def create_export(request, owner, fmt, ids):
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_ITEMS:
        raise ValueError(f"导出影像数量必须为 1-{MAX_ITEMS}")
    _validate_images(ids)
    return ExportJob.objects.create(owner=owner, format=fmt, imagery_ids=ids, expires_at=timezone.now() + timedelta(days=1))


def create_delivery_snapshot(*, owner, name, description="", imagery_ids):
    ids = list(dict.fromkeys(str(value) for value in imagery_ids))
    if not ids or len(ids) > MAX_ITEMS:
        raise ValueError(f"交付快照影像数量必须为 1-{MAX_ITEMS}")
    images = _validate_images(ids)
    manifest = {
        "type": "airmap-delivery-snapshot",
        "version": 1,
        "imagery": [
            {"id": image.id, "scene_key": image.scene_key, "source_name": image.source_name,
             "bbox": image.bbox, "acquisition_time": _json_default(image.acquisition_time) if image.acquisition_time else None,
             "metadata": _metadata(image),
             "assets": [{"role": asset.role, "name": asset.name, "size_bytes": asset.size_bytes, "checksum_sha256": asset.checksum_sha256} for asset in image.assets.all()]}
            for image in images
        ],
    }
    return DeliverySnapshot.objects.create(owner=owner, name=name.strip(), description=description.strip(), imagery_ids=ids, manifest=manifest)


def _stac(request, image, expires=None):
    metadata = _metadata(image)
    return build_stac_item_from_metadata(scene_key=image.scene_key, image_id=image.id, metadata=metadata,
        asset_hrefs={role: asset_url(request, image.id, role, expires) for role in image.assets.values_list("role", flat=True)})


def run_export(job):
    request = getattr(run_export, "request", None)
    # Worker has no request; URLs remain stable API-relative URLs.
    base = getattr(settings, "PUBLIC_SERVICE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    class Request:
        def build_absolute_uri(self, path): return base + path
    request = request or Request()
    images = _validate_images(job.imagery_ids)
    signed_expiry = int(job.expires_at.timestamp()) if job.expires_at else None
    records = build_records(request, images, signed_expiry)
    root = Path(getattr(settings, "EXPORTS_DIR", Path(settings.BASE_DIR) / "exports"))
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{job.id}.json" if job.format in (ExportJob.FORMAT_MANIFEST, ExportJob.FORMAT_STAC) else root / f"{job.id}.zip"
    fd, temp_name = tempfile.mkstemp(prefix=f"{job.id}.", dir=root)
    os.close(fd)
    temp = Path(temp_name)
    try:
        if job.format == ExportJob.FORMAT_MANIFEST:
            payload = {"type": "airmap-manifest", "version": 1, "items": records}
            temp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default, indent=2), encoding="utf-8")
        elif job.format == ExportJob.FORMAT_STAC:
            payload = {"type": "FeatureCollection", "stac_version": "1.0.0", "features": [_stac(request, x, signed_expiry) for x in images]}
            temp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default, indent=2), encoding="utf-8")
        else:
            checksums = []
            used_scene_names = set()
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
                manifest = {"type": "airmap-manifest", "version": 1, "items": records}
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, default=_json_default, indent=2))
                manifest_digest = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, default=_json_default, indent=2).encode("utf-8")).hexdigest()
                checksums.append(f"{manifest_digest}  manifest.json")
                for image in images:
                    scene_name = safe_archive_component(image.scene_key)
                    if scene_name in used_scene_names:
                        scene_name = f"{scene_name}_{safe_archive_component(image.id, 'image')[:24]}"
                    used_scene_names.add(scene_name)
                    for asset in image.assets.all():
                        try:
                            source = resolve_asset_path(asset)
                        except ValueError:
                            continue
                        filename = safe_archive_basename(asset.name or source.name, source.suffix or ".bin")
                        member = f"{scene_name}/{safe_archive_component(asset.role)}/{filename}"
                        # Asset roles are unique per scene, and the basename is normalized.
                        archive.write(source, member)
                        checksums.append(f"{file_sha256(source)}  {member}")
                checksums_text = "\n".join(checksums) + "\n"
                archive.writestr("checksums.sha256", checksums_text)
        temp.replace(target)
        job.file_path, job.file_size = str(target), target.stat().st_size
        return job
    finally:
        if temp.exists(): temp.unlink()


def process_pending(limit=10):
    processed = 0
    while processed < limit:
        with transaction.atomic():
            job = (ExportJob.objects.select_for_update()
                   .filter(status=ExportJob.STATUS_PENDING)
                   .order_by("created_at").first())
            if not job:
                break
            job.status, job.started_at = ExportJob.STATUS_RUNNING, timezone.now()
            job.save(update_fields=["status", "started_at"])
        try:
            run_export(job)
            job.status, job.finished_at = ExportJob.STATUS_DONE, timezone.now()
            job.save(update_fields=["status", "finished_at", "file_path", "file_size"])
        except Exception as exc:
            job.status, job.error, job.finished_at = ExportJob.STATUS_FAILED, str(exc), timezone.now()
            job.save(update_fields=["status", "error", "finished_at"])
        processed += 1
    return processed
