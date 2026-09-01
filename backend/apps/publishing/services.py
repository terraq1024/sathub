import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.imagery.models import ImageryAsset, ImageryRecord

from .models import ImageryService, ImageryServiceAsset, ServicePublishJob


SERVABLE_STATUSES = [ImageryService.STATUS_ONLINE, ImageryService.STATUS_DEGRADED]


@transaction.atomic
def create_publish_job(service: ImageryService, user) -> ServicePublishJob:
    service = ImageryService.objects.select_for_update().select_related("source_dataset").get(pk=service.pk)
    active = service.publish_jobs.filter(
        status__in=[ServicePublishJob.STATUS_PENDING, ServicePublishJob.STATUS_RUNNING],
    ).first()
    if active:
        return active

    if service.service_type == ImageryService.TYPE_DATASET_MOSAIC:
        dataset = service.source_dataset
        if not dataset:
            raise ValueError("Dataset service has no source dataset.")
        if dataset.status != dataset.STATUS_ACTIVE:
            raise ValueError("Archived datasets cannot be published.")
        source_snapshot = [
            str(imagery_id)
            for imagery_id in dataset.members.filter(enabled=True)
            .order_by("position", "id")
            .values_list("imagery_id", flat=True)
        ]
        target_revision = dataset.revision
    else:
        source_snapshot = [
            str(imagery_id)
            for imagery_id in service.service_assets.order_by("order", "id")
            .values_list("imagery_id", flat=True)
        ]
        target_revision = None

    if not _has_usable_publication(service):
        service.status = ImageryService.STATUS_PREPARING
        service.error_message = ""
        service.save(update_fields=["status", "error_message", "updated_at"])

    return ServicePublishJob.objects.create(
        service=service,
        created_by=user,
        source_snapshot=source_snapshot,
        target_revision=target_revision,
    )


def claim_publish_job():
    with transaction.atomic():
        job = ServicePublishJob.objects.select_for_update(skip_locked=True).filter(
            status=ServicePublishJob.STATUS_PENDING,
        ).order_by("id").first()
        if not job:
            return None
        job.status = ServicePublishJob.STATUS_RUNNING
        job.current_step = "validating"
        job.progress = 5
        job.started_at = timezone.now()
        job.save(update_fields=["status", "current_step", "progress", "started_at", "updated_at"])
        return job


def process_publish_job(job: ServicePublishJob) -> None:
    service = ImageryService.objects.select_related("source_dataset").prefetch_related(
        "service_assets__imagery",
    ).get(pk=job.service_id)
    had_usable_publication = _has_usable_publication(service)
    try:
        _set_service_stage(service, ImageryService.STATUS_VALIDATING, had_usable_publication)
        if service.service_type == ImageryService.TYPE_DATASET_MOSAIC:
            _publish_dataset(service, job, had_usable_publication)
        else:
            _publish_single_scene(service, job, had_usable_publication)
        _finish_job(job)
    except Exception as exc:
        _fail_publication(service, job, exc)


def _publish_single_scene(
    service: ImageryService,
    job: ServicePublishJob,
    had_usable_publication: bool,
) -> None:
    relation = service.service_assets.order_by("order", "id").first()
    if not relation:
        raise ValueError("Service has no imagery asset.")
    if getattr(relation.imagery, "is_archived", False):
        raise ValueError(f"Archived imagery cannot be published: {relation.imagery.pk}")
    source_asset = ImageryAsset.objects.filter(
        imagery=relation.imagery,
        role=ImageryAsset.ROLE_DATA,
    ).first()
    if not source_asset or not Path(source_asset.path).is_file():
        raise ValueError("The source imagery file is missing.")

    _update_job(job, "creating_cog", 20)
    _set_service_stage(service, ImageryService.STATUS_PREPARING, had_usable_publication)
    cog_path = Path(settings.COG_DIR) / f"{relation.imagery_id}.tif"
    _prepare_cog(relation.imagery, Path(source_asset.path), cog_path)
    _validate_cog_compatibility([cog_path])

    _update_job(job, "checking_titiler", 80)
    _set_service_stage(service, ImageryService.STATUS_PUBLISHING, had_usable_publication)
    titiler_base_url = settings.TITILER_BASE_URL.rstrip("/")
    _probe_cog(cog_path, titiler_base_url)
    render_config = _render_config_with_default_rescale(
        service.render_config,
        cog_path,
        titiler_base_url,
    )

    now = timezone.now()
    service.cog_path = str(cog_path.resolve())
    service.mosaic_path = ""
    service.titiler_base_url = titiler_base_url
    service.render_config = render_config
    service.status = ImageryService.STATUS_ONLINE
    service.error_message = ""
    service.published_at = now
    service.unpublished_at = None
    service.save(update_fields=[
        "cog_path", "mosaic_path", "titiler_base_url", "render_config", "status",
        "error_message", "published_at", "unpublished_at", "updated_at",
    ])


def _publish_dataset(
    service: ImageryService,
    job: ServicePublishJob,
    had_usable_publication: bool,
) -> None:
    dataset = service.source_dataset
    if not dataset:
        raise ValueError("Dataset service has no source dataset.")
    if dataset.status != dataset.STATUS_ACTIVE:
        raise ValueError("Archived datasets cannot be published.")

    snapshot = [str(value) for value in (job.source_snapshot or [])]
    if not snapshot:
        raise ValueError("The dataset has no enabled imagery.")
    if len(snapshot) != len(set(snapshot)):
        raise ValueError("The publication snapshot contains duplicate imagery.")

    imagery_by_id = {
        str(imagery.pk): imagery
        for imagery in ImageryRecord.objects.filter(pk__in=snapshot).prefetch_related("assets")
    }
    missing_ids = [imagery_id for imagery_id in snapshot if imagery_id not in imagery_by_id]
    if missing_ids:
        raise ValueError(f"Snapshot imagery not found: {', '.join(missing_ids[:5])}")

    ordered_imagery = [imagery_by_id[imagery_id] for imagery_id in snapshot]
    source_paths = []
    for imagery in ordered_imagery:
        if getattr(imagery, "is_archived", False):
            raise ValueError(f"Archived imagery cannot be published: {imagery.pk}")
        if not imagery.geometry or not _valid_bbox(imagery.bbox):
            raise ValueError(f"Imagery has no valid footprint: {imagery.pk}")
        data_asset = next(
            (asset for asset in imagery.assets.all() if asset.role == ImageryAsset.ROLE_DATA),
            None,
        )
        if not data_asset or not Path(data_asset.path).is_file():
            raise ValueError(f"Imagery data asset is missing: {imagery.pk}")
        source_paths.append(Path(data_asset.path))

    _update_job(job, "creating_cogs", 20)
    _set_service_stage(service, ImageryService.STATUS_PREPARING, had_usable_publication)
    cog_paths = []
    for imagery, source_path in zip(ordered_imagery, source_paths):
        cog_path = Path(settings.COG_DIR) / f"{imagery.pk}.tif"
        _prepare_cog(imagery, source_path, cog_path)
        cog_paths.append(cog_path)
    _, cog_metadata = _validate_cog_compatibility(cog_paths)

    mosaic_dir = Path(settings.MOSAIC_DIR)
    mosaic_dir.mkdir(parents=True, exist_ok=True)
    final_path = mosaic_dir / f"{service.service_key}.json"
    temporary_path = mosaic_dir / f".{service.service_key}.{job.pk}.{uuid.uuid4().hex}.tmp.json"
    backup_path = None
    try:
        _update_job(job, "creating_mosaic", 60)
        _build_mosaic_json(
            cog_paths,
            temporary_path,
            service.name,
            overview_minzoom=_overview_minzoom(cog_metadata),
        )

        titiler_base_url = settings.TITILER_BASE_URL.rstrip("/")
        render_config = _render_config_with_default_rescale(
            service.render_config,
            cog_paths[0],
            titiler_base_url,
        )
        _update_job(job, "checking_titiler", 80)
        _set_service_stage(service, ImageryService.STATUS_PUBLISHING, had_usable_publication)
        _probe_mosaic(
            temporary_path,
            titiler_base_url,
            render_config,
            cog_metadata[0]["bounds"],
        )

        if final_path.exists():
            backup_path = mosaic_dir / f".{service.service_key}.{uuid.uuid4().hex}.backup.json"
            shutil.copy2(final_path, backup_path)
        os.replace(temporary_path, final_path)
        try:
            _commit_dataset_publication(
                service,
                ordered_imagery,
                final_path,
                titiler_base_url,
                render_config,
                job.target_revision,
            )
        except Exception:
            if backup_path and backup_path.exists():
                os.replace(backup_path, final_path)
            else:
                final_path.unlink(missing_ok=True)
            raise
    finally:
        temporary_path.unlink(missing_ok=True)
        if backup_path:
            backup_path.unlink(missing_ok=True)


@transaction.atomic
def _commit_dataset_publication(
    service: ImageryService,
    ordered_imagery: list[ImageryRecord],
    mosaic_path: Path,
    titiler_base_url: str,
    render_config: dict,
    source_revision: int | None,
) -> None:
    service = ImageryService.objects.select_for_update().get(pk=service.pk)
    service.service_assets.all().delete()
    ImageryServiceAsset.objects.bulk_create([
        ImageryServiceAsset(service=service, imagery=imagery, order=position)
        for position, imagery in enumerate(ordered_imagery)
    ])
    now = timezone.now()
    service.cog_path = ""
    service.mosaic_path = str(mosaic_path.resolve())
    service.titiler_base_url = titiler_base_url
    service.render_config = render_config
    service.source_revision = source_revision
    service.status = ImageryService.STATUS_ONLINE
    service.error_message = ""
    service.published_at = now
    service.unpublished_at = None
    service.save(update_fields=[
        "cog_path", "mosaic_path", "titiler_base_url", "render_config",
        "source_revision", "status", "error_message", "published_at",
        "unpublished_at", "updated_at",
    ])


def _create_cog(source: Path, destination: Path) -> None:
    python = Path(settings.TITILER_PYTHON)
    converter = settings.BASE_DIR / "cog_convert.py"
    if not python.is_file():
        raise RuntimeError(f"TiTiler Python runtime is missing: {python}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.tmp.tif")
    try:
        result = subprocess.run(
            [str(python), str(converter), str(source), str(temporary_path)],
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "COG conversion failed.")[-4000:])
        if not temporary_path.is_file():
            raise RuntimeError("COG conversion did not create an output file.")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _prepare_cog(imagery: ImageryRecord, source: Path, destination: Path) -> None:
    """Create a reusable COG only when a service actually needs one."""
    if destination.is_file() and destination.stat().st_size > 0:
        imagery.__class__.objects.filter(pk=imagery.pk).update(
            cog_status=ImageryRecord.COG_READY,
            cog_path=str(destination.resolve()),
            cog_error="",
            cog_updated_at=timezone.now(),
            updated_at=timezone.now(),
        )
        try:
            from apps.imagery.services import sync_imagery_projection_safely

            sync_imagery_projection_safely(imagery.pk)
        except Exception:
            pass
        return
    imagery.__class__.objects.filter(pk=imagery.pk).update(
        cog_status=ImageryRecord.COG_PROCESSING,
        cog_error="",
        updated_at=timezone.now(),
    )
    try:
        _create_cog(source, destination)
    except Exception as exc:
        imagery.__class__.objects.filter(pk=imagery.pk).update(
            cog_status=ImageryRecord.COG_FAILED,
            cog_error=str(exc)[:4000],
            cog_updated_at=timezone.now(),
            updated_at=timezone.now(),
        )
        raise
    imagery.__class__.objects.filter(pk=imagery.pk).update(
        cog_status=ImageryRecord.COG_READY,
        cog_path=str(destination.resolve()),
        cog_error="",
        cog_updated_at=timezone.now(),
        updated_at=timezone.now(),
    )
    try:
        from apps.imagery.services import sync_imagery_projection_safely

        sync_imagery_projection_safely(imagery.pk)
    except Exception:
        pass


def _validate_cog_compatibility(
    cog_paths: list[Path],
) -> tuple[tuple[int, tuple[str, ...]], list[dict]]:
    metadata = _inspect_cogs(cog_paths)
    expected = None
    for path, item in zip(cog_paths, metadata):
        signature = (item["count"], tuple(item["dtypes"]))
        if expected is None:
            expected = signature
        elif signature != expected:
            raise ValueError(
                "Dataset imagery must have matching band counts and data types: "
                f"expected {expected}, got {signature} for {path.name}."
            )
    if expected is None:
        raise ValueError("No COG files were prepared.")
    return expected, metadata


def _inspect_cogs(cog_paths: list[Path]) -> list[dict]:
    python = Path(settings.TITILER_PYTHON)
    if not python.is_file():
        raise RuntimeError(f"TiTiler Python runtime is missing: {python}")
    script = """
import json
import sys

import rasterio
from rasterio.warp import transform_bounds

items = []
for source in json.load(sys.stdin):
    with rasterio.open(source) as dataset:
        if not dataset.crs:
            raise ValueError(f"COG has no CRS: {source}")
        items.append({
            "count": dataset.count,
            "dtypes": list(dataset.dtypes),
            "bounds": list(transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)),
        })
sys.stdout.write(json.dumps(items))
"""
    result = subprocess.run(
        [str(python), "-c", script],
        input=json.dumps([str(path.resolve()) for path in cog_paths]),
        capture_output=True,
        text=True,
        timeout=5 * 60,
    )
    if result.returncode:
        raise ValueError((result.stderr or result.stdout or "Unable to inspect COG metadata.")[-4000:])
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("COG metadata inspector returned invalid JSON.") from exc
    if len(metadata) != len(cog_paths):
        raise ValueError("COG metadata inspector returned an incomplete result.")
    return metadata


def _overview_minzoom(cog_metadata: list[dict]) -> int:
    min_lon = min(item["bounds"][0] for item in cog_metadata)
    min_lat = min(item["bounds"][1] for item in cog_metadata)
    max_lon = max(item["bounds"][2] for item in cog_metadata)
    max_lat = max(item["bounds"][3] for item in cog_metadata)
    span = max(max_lon - min_lon, max_lat - min_lat)
    if span <= 0:
        return 0
    return max(0, min(22, math.ceil(math.log2(360.0 / span))))


def _build_mosaic_json(
    cog_paths: list[Path],
    destination: Path,
    name: str,
    *,
    overview_minzoom: int,
) -> None:
    python = Path(settings.TITILER_PYTHON)
    if not python.is_file():
        raise RuntimeError(f"TiTiler Python runtime is missing: {python}")
    script = (
        "import json,sys;"
        "from cogeo_mosaic.mosaic import MosaicJSON;"
        "payload=json.load(sys.stdin);"
        "mosaic=MosaicJSON.from_urls(payload['urls'],quiet=True);"
        "target=min(mosaic.minzoom,payload['overview_minzoom']);"
        "mosaic=MosaicJSON.from_urls(payload['urls'],minzoom=target,maxzoom=mosaic.maxzoom,quiet=True) if target < mosaic.minzoom else mosaic;"
        "mosaic.name=payload['name'];"
        "sys.stdout.write(mosaic.model_dump_json(exclude_none=True))"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        input=json.dumps({
            "urls": [str(path.resolve()) for path in cog_paths],
            "name": name,
            "overview_minzoom": overview_minzoom,
        }),
        capture_output=True,
        text=True,
        timeout=60 * 60,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "MosaicJSON generation failed.")[-4000:])
    try:
        content = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("MosaicJSON generator returned invalid JSON.") from exc
    if not content.get("tiles"):
        raise RuntimeError("MosaicJSON contains no indexed tiles.")
    destination.write_text(json.dumps(content, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")


def _probe_cog(cog_path: Path, titiler_base_url: str) -> None:
    query = urlencode({"url": str(cog_path.resolve())})
    endpoint = f"{titiler_base_url}/cog/info?{query}"
    with urlopen(endpoint, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"TiTiler returned HTTP {response.status}.")


def _probe_mosaic(
    mosaic_path: Path,
    titiler_base_url: str,
    render_config: dict,
    first_cog_bounds: list,
) -> None:
    source = _titiler_mosaic_source(mosaic_path)
    info_endpoint = f"{titiler_base_url}/mosaicjson/info?{urlencode({'url': source})}"
    with urlopen(info_endpoint, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"TiTiler mosaic info returned HTTP {response.status}.")

    definition = json.loads(mosaic_path.read_text(encoding="utf-8"))
    lon = float(first_cog_bounds[0] + first_cog_bounds[2]) / 2
    lat = float(first_cog_bounds[1] + first_cog_bounds[3]) / 2
    z = max(0, min(22, int(definition["minzoom"])))
    x, y = _web_mercator_tile(lon, lat, z)
    query = _render_query(render_config, {"url": source, "pixel_selection": "first"})
    tile_endpoint = (
        f"{titiler_base_url}/mosaicjson/tiles/WebMercatorQuad/{z}/{x}/{y}.png?"
        f"{urlencode(query, doseq=True)}"
    )
    with urlopen(tile_endpoint, timeout=120) as response:
        if response.status != 200 or not response.read(1):
            raise RuntimeError("TiTiler mosaic center tile probe returned no image.")


def _render_config_with_default_rescale(
    render_config: dict | None,
    cog_path: Path,
    titiler_base_url: str,
) -> dict:
    config = dict(render_config or {})
    if config.get("rescale"):
        return config
    query = urlencode({"url": str(cog_path.resolve())})
    endpoint = f"{titiler_base_url}/cog/statistics?{query}"
    with urlopen(endpoint, timeout=120) as response:
        statistics = json.load(response)
    first_band = next(iter(statistics.values()), {})
    low = first_band.get("percentile_2")
    high = first_band.get("percentile_98")
    if low is not None and high is not None and high > low:
        config["rescale"] = f"{low},{high}"
    return config


def _render_query(config: dict | None, initial: dict | None = None) -> dict:
    query = dict(initial or {})
    for key in ["rescale", "colormap_name", "bidx", "expression"]:
        value = (config or {}).get(key)
        if value not in (None, "", []):
            query[key] = value
    return query


def titiler_tile_url(service: ImageryService, z: int, x: int, y: int) -> str:
    if service.service_type == ImageryService.TYPE_DATASET_MOSAIC:
        query = _render_query(service.render_config, {
            "url": _titiler_mosaic_source(Path(service.mosaic_path)),
            "pixel_selection": "first",
        })
        route = "mosaicjson"
    else:
        query = _render_query(service.render_config, {"url": service.cog_path})
        route = "cog"
    return (
        f"{service.titiler_base_url}/{route}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?"
        f"{urlencode(query, doseq=True)}"
    )


def service_zoom_range(service: ImageryService) -> tuple[int, int]:
    if service.service_type != ImageryService.TYPE_DATASET_MOSAIC or not service.mosaic_path:
        return 0, 22
    try:
        definition = json.loads(Path(service.mosaic_path).read_text(encoding="utf-8"))
        return int(definition.get("minzoom", 0)), int(definition.get("maxzoom", 22))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0, 22


def _titiler_mosaic_source(path: Path) -> str:
    resolved = str(path.resolve())
    if os.name == "nt" and path.drive and not resolved.startswith("\\\\?\\"):
        return f"\\\\?\\{resolved}"
    return resolved


def _web_mercator_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat = max(-85.05112878, min(85.05112878, lat))
    size = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * size)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * size)
    return max(0, min(size - 1, x)), max(0, min(size - 1, y))


def _valid_bbox(value) -> bool:
    return bool(
        isinstance(value, (list, tuple))
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _has_usable_publication(service: ImageryService) -> bool:
    if service.status not in SERVABLE_STATUSES:
        return False
    if service.service_type == ImageryService.TYPE_DATASET_MOSAIC:
        return bool(service.mosaic_path and Path(service.mosaic_path).is_file())
    return bool(service.cog_path and Path(service.cog_path).is_file())


def _set_service_stage(service: ImageryService, stage: str, preserve_online: bool) -> None:
    if preserve_online:
        return
    service.status = stage
    service.save(update_fields=["status", "updated_at"])


def _update_job(job: ServicePublishJob, step: str, progress: int) -> None:
    job.current_step = step
    job.progress = progress
    job.save(update_fields=["current_step", "progress", "updated_at"])


def _finish_job(job: ServicePublishJob) -> None:
    now = timezone.now()
    job.status = ServicePublishJob.STATUS_DONE
    job.current_step = "online"
    job.progress = 100
    job.finished_at = now
    job.error_message = ""
    job.save(update_fields=[
        "status", "current_step", "progress", "finished_at", "error_message", "updated_at",
    ])


def _fail_publication(service: ImageryService, job: ServicePublishJob, exc: Exception) -> None:
    message = str(exc)[:4000]
    service.refresh_from_db()
    service.status = (
        ImageryService.STATUS_DEGRADED
        if _has_usable_publication(service)
        else ImageryService.STATUS_FAILED
    )
    service.error_message = message
    service.save(update_fields=["status", "error_message", "updated_at"])
    job.status = ServicePublishJob.STATUS_FAILED
    job.error_message = message
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
