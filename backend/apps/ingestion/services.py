import hashlib
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.imagery.duckdb_index import upsert_image
from apps.imagery.metadata import build_scene_key, is_image_file, parse_product_group, scan_product_groups
from apps.imagery.models import ImageryAsset, ImageryProjectTag, ImageryRecord

from apps.storage_manager.models import StorageEndpoint, StorageObject

from apps.imagery.services import refresh_on_ingestion_datasets, sync_imagery_projection_safely
from apps.imagery.stac import build_stac_item_from_metadata
from apps.projects.models import Project
from apps.projects.services import user_can_access_project

from .models import IngestionItem, IngestionJob


def get_project_for_user(user, project_id):
    if project_id in (None, ""):
        return None
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"project_id": "Project does not exist."})
    if not user_can_access_project(user, project):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("You do not have access to this project.")
    return project


@transaction.atomic
def create_url_import_job(*, user, project_id, urls: list[str]) -> IngestionJob:
    project = get_project_for_user(user, project_id)
    job = IngestionJob.objects.create(
        created_by=user,
        project=project,
        source_type=IngestionJob.SOURCE_URL_TEXT,
        total_count=len(urls),
        source_payload={"urls": urls},
    )
    IngestionItem.objects.bulk_create([
        IngestionItem(job=job, source=url, source_kind=IngestionItem.SOURCE_URL)
        for url in urls
    ])
    return job


@transaction.atomic
def create_archive_upload_job(*, user, project_id, uploaded_file) -> IngestionJob:
    project = get_project_for_user(user, project_id)
    safe_name = Path(uploaded_file.name).name
    if not safe_name.lower().endswith((".zip", ".7z")):
        raise ValueError("Only .zip and .7z files are supported.")
    job = IngestionJob.objects.create(
        created_by=user,
        project=project,
        source_type=IngestionJob.SOURCE_ZIP_UPLOAD if safe_name.lower().endswith(".zip") else IngestionJob.SOURCE_ARCHIVE_UPLOAD,
        total_count=0,
        source_payload={"filename": safe_name},
    )
    staging_dir = Path(settings.STAGING_DIR) / str(job.id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_path = staging_dir / safe_name
    _write_uploaded_file(uploaded_file, archive_path)
    IngestionItem.objects.create(
        job=job,
        source=safe_name,
        source_kind=IngestionItem.SOURCE_FILE,
        raw_path=str(archive_path),
        container=True,
    )
    job.source_payload["staging_path"] = str(archive_path)
    job.save(update_fields=["source_payload", "updated_at"])
    return job


def find_existing_archive(filename: str):
    return ImageryRecord.objects.filter(archive_filename=filename).order_by("created_at").first()


create_zip_upload_job = create_archive_upload_job


@transaction.atomic
def create_folder_upload_job(*, user, project_id, files, relative_paths) -> IngestionJob:
    project = get_project_for_user(user, project_id)
    job = IngestionJob.objects.create(
        created_by=user,
        project=project,
        source_type=IngestionJob.SOURCE_FOLDER_UPLOAD,
        source_payload={"file_count": len(files)},
    )
    folder_dir = Path(settings.STAGING_DIR) / str(job.id) / "folder"
    folder_dir.mkdir(parents=True, exist_ok=True)
    for uploaded_file, relative_path in zip(files, relative_paths):
        target = _safe_join(folder_dir, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_uploaded_file(uploaded_file, target)
    IngestionItem.objects.create(
        job=job,
        source="folder",
        source_kind=IngestionItem.SOURCE_FOLDER_FILE,
        raw_path=str(folder_dir),
        container=True,
    )
    job.source_payload["staging_path"] = str(folder_dir)
    job.save(update_fields=["source_payload", "updated_at"])
    return job


def _write_uploaded_file(uploaded_file, destination: Path):
    if getattr(uploaded_file, "size", 0) > settings.MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file exceeds the configured size limit.")
    with destination.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)


def _safe_join(root: Path, relative_path: str) -> Path:
    normalized = str(relative_path).replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe relative path: {relative_path}")
    target = (root / Path(*path.parts)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe relative path: {relative_path}")
    return target


def retry_item(item: IngestionItem) -> IngestionItem:
    item.status = IngestionItem.STATUS_PENDING
    item.error_message = ""
    item.retry_count += 1
    item.save(update_fields=["status", "error_message", "retry_count", "updated_at"])
    job = item.job
    if job.status in {IngestionJob.STATUS_FAILED, IngestionJob.STATUS_DONE}:
        job.status = IngestionJob.STATUS_PENDING
        job.finished_at = None
        job.save(update_fields=["status", "finished_at", "updated_at"])
    return item


def run_pending_jobs(*, limit: int | None = None) -> int:
    from django.db import close_old_connections

    close_old_connections()
    _recover_stuck_items()
    queryset = IngestionJob.objects.filter(
        status__in=[IngestionJob.STATUS_PENDING, IngestionJob.STATUS_RUNNING, IngestionJob.STATUS_SCANNING]
    ).order_by("created_at")
    if limit:
        queryset = queryset[:limit]
    count = 0
    for job in queryset:
        try:
            process_job(job)
        except Exception:
            import logging

            logging.getLogger("apps.ingestion").exception("Ingestion job %s crashed", job.pk)
            job.status = IngestionJob.STATUS_FAILED
            job.error_message = "Worker crashed while processing this job; item states were reset for retry."
            job.save(update_fields=["status", "error_message", "updated_at"])
        count += 1
    return count


# Items left in an intermediate state by a crashed worker can never be picked up
# again by the pending filter, wedging their job in RUNNING forever. Anything
# not actively being written by this process is older than the staleness window
# and gets reset to PENDING so the next pass retries or fails it normally.
STUCK_ITEM_STATUSES = [
    IngestionItem.STATUS_DOWNLOADING,
    IngestionItem.STATUS_EXTRACTING,
    IngestionItem.STATUS_SCANNING,
    IngestionItem.STATUS_PARSING,
    IngestionItem.STATUS_STORING,
]


def _recover_stuck_items(older_than_minutes: int = 30) -> int:
    cutoff = timezone.now() - timezone.timedelta(minutes=older_than_minutes)
    stale = IngestionItem.objects.filter(status__in=STUCK_ITEM_STATUSES, updated_at__lt=cutoff)
    count = stale.count()
    if count:
        stale.update(status=IngestionItem.STATUS_PENDING, error_message="", updated_at=timezone.now())
    return count


def process_job(job: IngestionJob) -> None:
    job.status = IngestionJob.STATUS_RUNNING
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    while True:
        item = job.items.filter(status=IngestionItem.STATUS_PENDING).order_by("id").first()
        if item is None:
            break
        process_item(item)
    refresh_job_counts(job)
    if job.status == IngestionJob.STATUS_DONE and job.success_count:
        refresh_on_ingestion_datasets()


def refresh_job_counts(job: IngestionJob) -> None:
    leaf_items = job.items.filter(container=False)
    container_failures = job.items.filter(container=True, status=IngestionItem.STATUS_FAILED)
    total = leaf_items.count()
    success = leaf_items.filter(status=IngestionItem.STATUS_DONE).count()
    skipped = leaf_items.filter(status=IngestionItem.STATUS_SKIPPED).count()
    failed = leaf_items.filter(status=IngestionItem.STATUS_FAILED).count()
    warnings = leaf_items.exclude(metadata_status__in=["", "ready"]).count()
    has_pending = job.items.filter(status__in=[IngestionItem.STATUS_PENDING, IngestionItem.STATUS_DOWNLOADING, IngestionItem.STATUS_EXTRACTING, IngestionItem.STATUS_SCANNING, IngestionItem.STATUS_PARSING, IngestionItem.STATUS_STORING]).exists()
    job.total_count = total or job.total_count
    job.success_count = success
    job.skipped_count = skipped
    job.failed_count = failed
    job.warning_count = warnings
    if not has_pending:
        # A container can fail before product children are created. That must
        # remain a failed job instead of becoming a misleading zero-item done.
        job.status = IngestionJob.STATUS_FAILED if failed or container_failures.exists() else IngestionJob.STATUS_DONE
        job.finished_at = timezone.now()
        if container_failures.exists() and not job.error_message:
            job.error_message = container_failures.first().error_message
    job.save(update_fields=["total_count", "success_count", "skipped_count", "failed_count", "warning_count", "status", "error_message", "finished_at", "updated_at"])


def process_item(item: IngestionItem) -> None:
    try:
        if item.container:
            source_path = _materialize_item(item)
            _scan_container(item, source_path)
            return
        if item.source_kind == IngestionItem.SOURCE_URL and not item.raw_path:
            item.status = IngestionItem.STATUS_DOWNLOADING
            item.save(update_fields=["status", "updated_at"])
            item.raw_path = str(_download_url(item))
            item.save(update_fields=["raw_path", "updated_at"])
        if item.raw_path and Path(item.raw_path).is_file() and _is_archive(Path(item.raw_path)):
            _scan_archive(item, Path(item.raw_path))
            return
        if item.raw_path and Path(item.raw_path).is_dir():
            group = next((candidate for candidate in scan_product_groups(item.raw_path) if candidate.stem == item.source), None)
            if group is None:
                raise ValueError(f"Product group not found: {item.source}")
            _index_group_item(item, group)
            return
        if item.raw_path and Path(item.raw_path).is_file() and is_image_file(item.raw_path):
            groups = scan_product_groups(Path(item.raw_path).parent)
            group = next((candidate for candidate in groups if candidate.stem == Path(item.raw_path).stem), None)
            if group is None:
                raise ValueError(f"Image product group not found: {item.raw_path}")
            _index_group_item(item, group)
            return
        raise ValueError(f"Unsupported ingestion item: {item.source}")
    except Exception as exc:
        item.status = IngestionItem.STATUS_FAILED
        item.error_message = str(exc)
        item.save(update_fields=["status", "error_message", "updated_at"])


def _materialize_item(item: IngestionItem) -> Path:
    if item.source_kind == IngestionItem.SOURCE_URL:
        return _download_url(item)
    if not item.raw_path:
        raise ValueError("Missing staging path")
    return Path(item.raw_path)


def _download_url(item: IngestionItem) -> Path:
    parsed = urllib.parse.urlparse(item.source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS URLs are supported.")
    staging_dir = Path(settings.STAGING_DIR) / str(item.job_id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(parsed.path).name or f"download-{item.id}"
    if not Path(filename).suffix:
        filename += ".download"
    destination = _safe_join(staging_dir, filename)
    with urllib.request.urlopen(item.source, timeout=settings.URL_DOWNLOAD_TIMEOUT) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > settings.MAX_UPLOAD_BYTES:
            raise ValueError("Remote file exceeds the configured size limit.")
        with destination.open("wb") as output:
            copied = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > settings.MAX_UPLOAD_BYTES:
                    raise ValueError("Remote file exceeds the configured size limit.")
                output.write(chunk)
    return destination


def _is_archive(path: Path) -> bool:
    if zipfile.is_zipfile(path):
        return True
    try:
        import py7zr

        return py7zr.is_7zfile(path)
    except (ImportError, OSError):
        return path.suffix.lower() == ".7z"


def _validate_member_path(name: str, root: Path):
    _safe_join(root, name)


def _scan_archive(item: IngestionItem, archive_path: Path):
    item.status = IngestionItem.STATUS_EXTRACTING
    item.save(update_fields=["status", "updated_at"])
    extract_dir = Path(settings.STAGING_DIR) / str(item.job_id) / f"extract-{item.id}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            total = 0
            for member in archive.infolist():
                _validate_member_path(member.filename, extract_dir)
                total += member.file_size
                if total > settings.MAX_EXTRACTED_BYTES:
                    raise ValueError("Archive expanded size exceeds the configured limit.")
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = _safe_join(extract_dir, member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    else:
        import py7zr

        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            members = archive.list()
            total = 0
            for member in members:
                _validate_member_path(member.filename, extract_dir)
                total += getattr(member, "uncompressed", 0) or 0
                if total > settings.MAX_EXTRACTED_BYTES:
                    raise ValueError("Archive expanded size exceeds the configured limit.")
        tar_executable = shutil.which("tar")
        if tar_executable:
            result = subprocess.run(
                [tar_executable, "-xf", str(archive_path), "-C", str(extract_dir)],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                raise ValueError(f"7Z extraction failed: {detail or 'tar returned a non-zero exit code.'}")
        else:
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                archive.extractall(path=extract_dir)
    _scan_extracted_directory(item, extract_dir)


def _scan_container(item: IngestionItem, source_path: Path):
    if source_path.is_file() and _is_archive(source_path):
        _scan_archive(item, source_path)
        return
    _scan_extracted_directory(item, source_path)


def _scan_extracted_directory(item: IngestionItem, extract_dir: Path):
    item.status = IngestionItem.STATUS_SCANNING
    item.save(update_fields=["status", "updated_at"])
    groups = scan_product_groups(extract_dir)
    if not groups:
        raise ValueError("No supported imagery product group was found.")
    existing = set(item.job.items.filter(container=False).values_list("source", flat=True))
    children = []
    for group in groups:
        if group.stem in existing:
            continue
        children.append(IngestionItem(
            job=item.job,
            parent=item,
            source=group.stem,
            source_kind=IngestionItem.SOURCE_ARCHIVE_MEMBER,
            raw_path=str(extract_dir),
            relative_path=str((group.data_path or group.metadata_path).relative_to(extract_dir)),
        ))
    IngestionItem.objects.bulk_create(children)
    item.status = IngestionItem.STATUS_DONE
    item.save(update_fields=["status", "updated_at"])
    item.job.total_count = item.job.items.filter(container=False).count()
    item.job.save(update_fields=["total_count", "updated_at"])


def _copy_asset(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _warp_preview_north_up(source: Path, destination: Path) -> Path | None:
    """Warp a rotated raster into an axis-aligned EPSG:4326 preview JPEG.

    The raster warp runs in the TiTiler subprocess (the main runtime cannot
    import rasterio); this side only decodes the returned array and encodes
    it as a normalized JPEG.
    """
    python = Path(settings.TITILER_PYTHON)
    if not python.is_file():
        import sys

        python = Path(sys.executable)
    script = Path(__file__).resolve().parent.parent / "imagery" / "preview_warper.py"
    if not script.is_file():
        return None
    try:
        result = subprocess.run(
            [str(python), str(script)],
            input=json.dumps({"source": str(source), "max_size": 2400}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        payload = json.loads(result.stdout or "{}")
        if not payload.get("ok"):
            return None
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
        Image.fromarray(normalized, mode="L").save(destination, format="JPEG", quality=88, optimize=True)
        return destination
    except Exception:
        return None


def generate_preview_image(source: Path, destination: Path) -> Path | None:
    """Create a small RGB/JPEG preview from a raster without reading full-size pixels when overviews exist.

    Rotated rasters (Umbra spotlight GEC and similar north-east-up products)
    are warped to an axis-aligned EPSG:4326 grid first; without the warp the
    preview bitmap would shear once Leaflet stretches it over the bbox.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tifffile

        with tifffile.TiffFile(str(source)) as tif:
            tag = tif.pages[0].tags.get("ModelTransformationTag") if tif.pages else None
            values = tag.value if tag is not None else None
        if values is not None and len(values) >= 2:
            from math import atan2, degrees

            a, b = float(values[0]), float(values[1])
            scale = (abs(a) + abs(b)) or 1.0
            if abs(b) / scale > 1e-6 and abs(degrees(atan2(b, a))) > 0.5:
                warped = _warp_preview_north_up(source, destination)
                if warped:
                    return warped
    except Exception:
        pass
    try:
        import numpy as np
        import tifffile
        from PIL import Image

        with tifffile.TiffFile(str(source)) as tif:
            if not tif.pages:
                return None
            array = tif.pages[-1].asarray()
        array = np.asarray(array)
        if np.iscomplexobj(array):
            array = np.abs(array)
        if array.ndim > 2:
            array = array[0] if array.shape[0] <= 4 else array[..., 0]
        if array.ndim != 2 or not array.size:
            return None
        array = array.astype("float32", copy=False)
        finite = array[np.isfinite(array)]
        if not finite.size:
            return None
        low, high = np.percentile(finite, [2, 98])
        if high <= low:
            high = low + 1
        normalized = np.clip((array - low) * 255 / (high - low), 0, 255).astype("uint8")
        image = Image.fromarray(normalized, mode="L")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        image.save(destination, format="JPEG", quality=88, optimize=True)
        return destination
    except Exception:
        try:
            from PIL import Image

            with Image.open(source) as image:
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                image.convert("L").save(destination, format="JPEG", quality=88, optimize=True)
            return destination
        except Exception:
            return None


def _serializable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    return value


def _asset_specs(group, root: Path, destination: Path, generated_preview: Path | None = None):
    specs = []
    source_by_role = {
        "data": group.data_path,
        "preview": group.preview_path or generated_preview,
        "thumbnail": group.files.get("thumbnail.jpg") or group.files.get("thumbnail.png"),
        "metadata": group.metadata_path,
        "incidence": group.files.get("incidence.xml"),
        "log": group.files.get("log"),
    }
    for role, source in source_by_role.items():
        if not source:
            continue
        target = destination / role / source.name
        specs.append((role, source, target))
    return specs


def _reference_object_for_path(job, source: Path):
    if job.source_type != IngestionJob.SOURCE_STORAGE_REFERENCE:
        return None
    endpoint_id = (job.source_payload or {}).get("storage_endpoint_id")
    if not endpoint_id:
        return None
    endpoint = StorageEndpoint.objects.get(pk=endpoint_id)
    root = Path(endpoint.root_uri).resolve()
    resolved = source.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("存储引用文件超出了已登记存储源根目录。")
    key = str(resolved.relative_to(root)).replace("\\", "/")
    return StorageObject.objects.filter(endpoint=endpoint, object_key=key).first()


def _index_group_item(item: IngestionItem, group):
    item.status = IngestionItem.STATUS_PARSING
    item.save(update_fields=["status", "updated_at"])
    metadata = _parse_group_metadata(group)
    scene_key, identity_hash = build_scene_key(metadata)
    generated_preview = None
    preview_policy = "source_preview" if group.preview_path else "generated_preview"
    if not group.preview_path and group.data_path:
        generated_preview = generate_preview_image(
            Path(group.data_path),
            Path(settings.STAGING_DIR) / "previews" / f"{item.id}.jpg",
        )
        if generated_preview:
            metadata["preview_status"] = "ready"
            metadata["preview_source"] = "generated"
    metadata.setdefault("raw_metadata", {})["preview_policy"] = preview_policy
    archive_filename = None
    archive_job_id = None
    if item.job.source_type in {IngestionJob.SOURCE_ARCHIVE_UPLOAD, IngestionJob.SOURCE_ZIP_UPLOAD}:
        archive_filename = item.job.source_payload.get("filename")
        archive_job_id = item.job_id
    # Archive-level de-duplication is performed before upload. This check is
    # only a concurrent-job guard; products within the same archive may differ.
    existing = None
    if archive_filename:
        existing = ImageryRecord.objects.filter(archive_filename=archive_filename).exclude(archive_job_id=archive_job_id).order_by("created_at").first()
    else:
        existing = ImageryRecord.objects.filter(identity_hash=identity_hash).first()
    if existing:
        _mark_duplicate(item, existing, scene_key, metadata)
        return

    image_id = uuid.uuid4().hex
    try:
        with transaction.atomic():
            record = ImageryRecord.objects.create(
                id=image_id,
                scene_key=scene_key,
                identity_hash=identity_hash,
                stac_id=scene_key,
                source_name=metadata["source_name"],
                archive_filename=archive_filename,
                archive_job_id=archive_job_id,
                platform_code=metadata.get("platform_code") or "",
                satellite_name=metadata.get("satellite_name") or "",
                sensor=metadata.get("sensor") or "",
                imaging_mode=metadata.get("imaging_mode") or "",
                imaging_mode_detail=metadata.get("imaging_mode_detail") or "",
                polarization=metadata.get("polarization") or "",
                polarizations=metadata.get("polarizations") or [],
                product_level=metadata.get("product_level") or "",
                acquisition_time=metadata.get("acquisition_time"),
                acquisition_start=metadata.get("acquisition_start"),
                acquisition_end=metadata.get("acquisition_end"),
                time_assumption=metadata.get("time_assumption") or "",
                orbit_id=metadata.get("orbit_id") or "",
                orbit_direction=metadata.get("orbit_direction") or "",
                look_side=metadata.get("look_side") or "",
                resolution_m=metadata.get("resolution_m"),
                pixel_spacing_range_m=metadata.get("pixel_spacing_range_m"),
                pixel_spacing_azimuth_m=metadata.get("pixel_spacing_azimuth_m"),
                width=metadata.get("width"),
                height=metadata.get("height"),
                incidence_angle_near_deg=metadata.get("incidence_angle_near_deg"),
                incidence_angle_far_deg=metadata.get("incidence_angle_far_deg"),
                geometry=metadata.get("geometry"),
                bbox=metadata.get("bbox"),
                epsg=metadata.get("epsg"),
                metadata_status=metadata.get("metadata_status") or "partial",
                spatial_status=metadata.get("spatial_status") or "partial",
                preview_status=metadata.get("preview_status") or "missing",
                metadata_sources=metadata.get("metadata_sources") or [],
                raw_metadata=_serializable(metadata.get("raw_metadata") or {}),
                first_uploaded_by=item.job.created_by,
                status=ImageryRecord.STATUS_READY if metadata.get("metadata_status") == "ready" else ImageryRecord.STATUS_PARTIAL,
                cog_status=ImageryRecord.COG_NONE,
            )
            if item.job.project_id:
                ImageryProjectTag.objects.create(imagery=record, project_id=item.job.project_id)
            destination = Path(settings.IMAGERY_DIR) / scene_key
            asset_hrefs = {}
            asset_paths = {}
            for role, source, target in _asset_specs(group, Path(item.raw_path), destination, generated_preview):
                endpoint_id = (item.job.source_payload or {}).get("storage_endpoint_id") if item.job.source_type == IngestionJob.SOURCE_STORAGE_REFERENCE else None
                endpoint = StorageEndpoint.objects.filter(pk=endpoint_id).first() if endpoint_id else None
                referenced_object = None
                if (not endpoint or endpoint.mode == StorageEndpoint.MODE_REFERENCE) and source != generated_preview:
                    try:
                        referenced_object = _reference_object_for_path(item.job, source)
                    except ValueError:
                        # Platform-derived assets (generated previews) live in
                        # staging and are never registered storage objects.
                        referenced_object = None
                if referenced_object:
                    stored_path = source.resolve()
                    access_mode = ImageryAsset.ACCESS_REFERENCE
                else:
                    stored_path = _copy_asset(source, target)
                    access_mode = ImageryAsset.ACCESS_MANAGED
                checksum = hashlib.sha256(stored_path.read_bytes()).hexdigest() if stored_path.stat().st_size < 64 * 1024 * 1024 else ""
                ImageryAsset.objects.create(imagery=record, role=role, name=source.name, path=str(stored_path), storage_object=referenced_object, access_mode=access_mode, media_type=_media_type(role, source), size_bytes=stored_path.stat().st_size, checksum_sha256=checksum)
                asset_hrefs[role] = f"/api/imagery/{image_id}/assets/{role}"
                asset_paths[role] = str(stored_path)
            stac_json = build_stac_item_from_metadata(scene_key=scene_key, image_id=image_id, metadata=metadata, asset_hrefs=asset_hrefs, project_ids=[str(item.job.project_id)] if item.job.project_id else [])
            stac_path = Path(settings.STAC_DIR) / "items" / f"{scene_key}.json"
            stac_path.parent.mkdir(parents=True, exist_ok=True)
            stac_path.write_text(json.dumps(stac_json, ensure_ascii=False, indent=2), encoding="utf-8")
            record.stac_path = str(stac_path)
            record.save(update_fields=["stac_path", "updated_at"])
            upsert_image(_duckdb_record(record, item, metadata, stac_json, asset_paths))
    except IntegrityError:
        existing = ImageryRecord.objects.filter(
            Q(identity_hash=identity_hash) | Q(scene_key=scene_key) | Q(stac_id=scene_key)
        ).first()
        if existing is None:
            raise
        _mark_duplicate(item, existing, scene_key, metadata)
        return
    item.status = IngestionItem.STATUS_DONE
    item.raw_path = metadata.get("data_path") or item.raw_path
    item.stac_id = scene_key
    item.image_id = image_id
    item.scene_key = scene_key
    item.metadata_status = metadata.get("metadata_status") or "partial"
    item.error_message = "" if item.metadata_status == "ready" else "Imported with partial metadata."
    item.save(update_fields=["status", "raw_path", "stac_id", "image_id", "scene_key", "metadata_status", "error_message", "updated_at"])
    try:
        from apps.audit_log.services import record_event

        record_event(
            actor=item.job.created_by,
            action="ingestion.item_completed",
            object_type="imagery",
            object_id=image_id,
            payload={"job_id": str(item.job_id), "scene_key": scene_key, "cog_status": ImageryRecord.COG_NONE},
        )
    except Exception:
        pass


def _mark_duplicate(item, existing, scene_key, metadata):
    if item.job.project_id:
        ImageryProjectTag.objects.get_or_create(imagery=existing, project_id=item.job.project_id)
        sync_imagery_projection_safely(existing.id)
    item.status = IngestionItem.STATUS_SKIPPED
    item.duplicate_of = existing
    item.image_id = existing.id
    item.stac_id = existing.stac_id
    item.scene_key = scene_key
    item.metadata_status = metadata.get("metadata_status") or "partial"
    item.error_message = "Duplicate scene skipped; existing imagery was reused."
    item.save(update_fields=["status", "duplicate_of", "image_id", "stac_id", "scene_key", "metadata_status", "error_message", "updated_at"])
    try:
        from apps.audit_log.services import record_event

        record_event(
            actor=item.job.created_by,
            action="ingestion.item_skipped_duplicate",
            object_type="imagery",
            object_id=existing.id,
            payload={"job_id": str(item.job_id), "scene_key": scene_key, "duplicate_of": existing.id},
        )
    except Exception:
        pass


def _parse_group_metadata(group):
    """Apply an active registry template as an overlay without weakening the legacy parser.

    Registry rules are intentionally additive: a template may define only the fields a
    supplier needs to govern, while the AIRSAT/generic parser remains responsible for
    paths, footprint and all fields not covered by that template.
    """
    fallback = parse_product_group(group)
    try:
        from apps.metadata_registry.engine import parse_product_group_with_registry

        parsed = parse_product_group_with_registry(group, fallback_callable=parse_product_group)
    except Exception:
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    registry_info = parsed.get("metadata_registry")
    if not registry_info:
        return fallback
    values = parsed.get("values") or {
        key: value
        for key, value in parsed.items()
        if key not in {"metadata_provenance", "metadata_quality_issues", "metadata_registry"}
    }
    merged = {**fallback}
    aliases = {"platform": "platform_code", "satellite": "satellite_name", "datetime": "acquisition_time"}
    for key, value in values.items():
        target = aliases.get(key, key)
        if value not in (None, "", []):
            merged[target] = value
    sources = list(merged.get("metadata_sources") or [])
    if registry_info:
        sources.append({"type": "registry", **registry_info})
    merged["metadata_sources"] = sources
    raw = dict(merged.get("raw_metadata") or {})
    raw["metadata_registry"] = {
        "values": values,
        "provenance": parsed.get("provenance") or parsed.get("metadata_provenance") or {},
        "issues": parsed.get("issues") or parsed.get("metadata_quality_issues") or [],
    }
    merged["raw_metadata"] = raw
    if parsed.get("issues") or parsed.get("metadata_quality_issues"):
        merged["metadata_status"] = "partial"
    return merged


def _media_type(role: str, source: Path | None = None) -> str:
    if source and source.suffix.lower() == ".json":
        return "application/geo+json" if role == "metadata" else "application/json"
    if source and source.suffix.lower() == ".png":
        return "image/png"
    return {"data": "image/tiff", "preview": "image/jpeg", "thumbnail": "image/jpeg", "metadata": "application/xml", "incidence": "application/xml", "log": "text/plain"}.get(role, "application/octet-stream")


def _duckdb_record(record, item, metadata, stac_json, asset_paths=None):
    asset_paths = asset_paths or {}
    bbox = metadata.get("bbox") or [None, None, None, None]
    return {
        "image_id": record.id,
        "stac_id": record.stac_id,
        "collection_id": "sathub-imagery",
        "scene_key": record.scene_key,
        "project_id": str(item.job.project_id) if item.job.project_id else "",
        "project_ids": "|".join(str(project_id) for project_id in record.project_tags.values_list("project_id", flat=True)),
        "owner_id": str(record.first_uploaded_by_id),
        "job_id": str(item.job_id),
        "item_id": str(item.id),
        "source_name": record.source_name,
        "file_path": asset_paths.get("data") or metadata.get("data_path"),
        "raw_path": asset_paths.get("data") or metadata.get("data_path"),
        "preview_path": asset_paths.get("preview") or metadata.get("preview_path"),
        "thumbnail_path": asset_paths.get("thumbnail") or metadata.get("thumbnail_path"),
        "platform": record.platform_code,
        "satellite_name": record.satellite_name,
        "sensor": record.sensor,
        "imaging_mode": record.imaging_mode,
        "imaging_mode_detail": record.imaging_mode_detail,
        "product_level": record.product_level,
        "polarization": record.polarization,
        "polarizations": record.polarizations,
        "resolution_m": record.resolution_m,
        "pixel_spacing_range_m": record.pixel_spacing_range_m,
        "pixel_spacing_azimuth_m": record.pixel_spacing_azimuth_m,
        "acquisition_time": record.acquisition_time.replace(tzinfo=None) if record.acquisition_time else None,
        "acquisition_start": record.acquisition_start.replace(tzinfo=None) if record.acquisition_start else None,
        "acquisition_end": record.acquisition_end.replace(tzinfo=None) if record.acquisition_end else None,
        "center_lon": _geometry_center(record.geometry)[0],
        "center_lat": _geometry_center(record.geometry)[1],
        "min_lon": bbox[0], "min_lat": bbox[1], "max_lon": bbox[2], "max_lat": bbox[3],
        "epsg": record.epsg,
        "spatial_status": record.spatial_status,
        "metadata_status": record.metadata_status,
        "preview_status": record.preview_status,
        "cog_status": record.cog_status,
        "cog_path": record.cog_path,
        "footprint_geojson": record.geometry,
        "stac_path": record.stac_path,
        "status": record.status,
        "stac_json": stac_json,
    }


def _geometry_center(geometry):
    if not geometry:
        return None, None
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates", [None, None])
        return coordinates[0], coordinates[1]
    bbox = geometry.get("bbox")
    if bbox:
        return (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    coordinates = geometry.get("coordinates") or []
    points = coordinates[0] if geometry.get("type") == "Polygon" and coordinates else coordinates
    if points:
        return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)
    return None, None
