from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.imagery.models import ImageryAsset

from .exceptions import ProcessingError
from .models import ProcessingJob


STDERR_LIMIT = 4000
DEFAULT_TIMEOUT_SECONDS = 60 * 60


def _error(message, code="processing_error", **details):
    return ProcessingError(code=code, message=message, details=details)


def _strict_child(path: Path, root: Path) -> bool:
    return path != root and root in path.parents


def source_path_for_imagery(imagery) -> Path:
    asset = ImageryAsset.objects.filter(
        imagery=imagery,
        role=ImageryAsset.ROLE_DATA,
    ).first()
    if not asset:
        raise _error("影像缺少主数据资产", "missing_source")
    try:
        source = Path(asset.path).resolve(strict=True)
        data_root = Path(settings.DATA_DIR).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _error("影像主数据路径无效", "invalid_source") from exc
    if not source.is_file():
        raise _error("影像主数据文件不存在", "missing_source")
    if not _strict_child(source, data_root):
        endpoint = getattr(asset, "storage_object", None)
        if not endpoint or not endpoint.endpoint:
            raise _error("影像主数据必须位于 DATA_DIR 内或已登记存储源内", "invalid_source")
        from apps.storage_manager.backends import validate_local_root

        root = validate_local_root(endpoint.endpoint.root_uri)
        if not _strict_child(source, root):
            raise _error("影像主数据不在登记存储源根目录内", "invalid_source")
    return source


def processing_root() -> Path:
    root = Path(settings.PROCESSING_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=True)


def job_output_directory(job_or_id) -> Path:
    root = processing_root()
    candidate = (root / str(getattr(job_or_id, "id", job_or_id))).resolve()
    if not _strict_child(candidate, root):
        raise _error("处理任务输出目录无效", "invalid_output")
    return candidate


def expected_output_path(job: ProcessingJob) -> Path:
    suffix = ".tif" if job.output_format == ProcessingJob.OUTPUT_GEOTIFF else ".png"
    return (job_output_directory(job) / f"result{suffix}").resolve()


def validated_download_path(job: ProcessingJob) -> Path:
    if not job.output_path:
        raise _error("处理结果尚未生成", "output_not_ready")
    try:
        stored = Path(job.output_path).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _error("处理结果文件不存在", "missing_output") from exc
    expected = expected_output_path(job)
    root = processing_root()
    if stored != expected or not _strict_child(stored, root) or not stored.is_file():
        raise _error("处理结果路径无效", "invalid_output")
    return stored


def remove_job_outputs(job: ProcessingJob) -> None:
    directory = job_output_directory(job)
    root = processing_root()
    if directory.exists():
        resolved = directory.resolve(strict=True)
        if not _strict_child(resolved, root):
            raise _error("拒绝清理 PROCESSING_DIR 之外的目录", "invalid_output")
        shutil.rmtree(resolved)


def _timeout_seconds() -> int:
    try:
        value = int(getattr(settings, "PROCESSING_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT_SECONDS
    return max(1, min(value, 24 * 60 * 60))


def _stderr_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = str(value).strip()
    if len(value) > STDERR_LIMIT:
        value = value[-STDERR_LIMIT:]
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return value
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])[-STDERR_LIMIT:]
    return value


def _worker_payload(job: ProcessingJob, source: Path, temporary: Path) -> dict:
    return {
        "source_path": str(source),
        "output_path": str(temporary),
        "crop_geometry_type": job.crop_geometry_type,
        "bbox": job.bbox,
        "geometry": job.geometry,
        "bands": job.bands,
        "expression": job.expression,
        "output_format": job.output_format,
    }


def _run_raster_subprocess(job: ProcessingJob, source: Path, temporary: Path) -> dict:
    python = Path(settings.TITILER_PYTHON).resolve()
    script = Path(__file__).with_name("raster_worker.py").resolve()
    if not python.is_file():
        raise _error("TiTiler Python 运行时不存在", "runtime_missing")
    if not script.is_file():
        raise _error("栅格处理脚本不存在", "worker_missing")
    try:
        result = subprocess.run(
            [str(python), str(script)],
            input=json.dumps(_worker_payload(job, source, temporary), ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_timeout_seconds(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        detail = _stderr_text(exc.stderr)
        message = "栅格处理超时"
        if detail:
            message = f"{message}：{detail}"
        raise _error(message, "processing_timeout") from exc
    except OSError as exc:
        raise _error("无法启动栅格处理运行时", "runtime_start_failed") from exc

    if result.returncode != 0:
        detail = _stderr_text(result.stderr or result.stdout)
        message = "栅格处理子进程执行失败"
        if detail:
            message = f"{message}：{detail}"
        raise _error(message, "processing_failed", returncode=result.returncode)
    try:
        metadata = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise _error("栅格处理子进程返回了无效结果", "invalid_worker_response") from exc
    if not isinstance(metadata, dict):
        raise _error("栅格处理子进程返回了无效结果", "invalid_worker_response")
    return metadata


def _mark_failed(job: ProcessingJob, exc: Exception) -> None:
    message = str(exc) if isinstance(exc, ProcessingError) else f"栅格处理失败：{exc}"
    ProcessingJob.objects.filter(pk=job.pk).update(
        status=ProcessingJob.STATUS_FAILED,
        error_message=message[-8000:],
        output_path="",
        output_media_type="",
        finished_at=timezone.now(),
        updated_at=timezone.now(),
    )
    job.refresh_from_db()


def _ensure_running(job: ProcessingJob) -> ProcessingJob:
    if job.status == ProcessingJob.STATUS_RUNNING:
        return job
    if job.status != ProcessingJob.STATUS_PENDING:
        raise _error("仅等待中的任务可以开始处理", "invalid_status")
    now = timezone.now()
    updated = ProcessingJob.objects.filter(
        pk=job.pk,
        status=ProcessingJob.STATUS_PENDING,
    ).update(
        status=ProcessingJob.STATUS_RUNNING,
        attempts=F("attempts") + 1,
        started_at=now,
        finished_at=None,
        error_message="",
        updated_at=now,
    )
    if not updated:
        raise _error("任务已被其他处理进程领取", "job_already_claimed")
    job.refresh_from_db()
    return job


def process_job(job: ProcessingJob) -> Path:
    job = _ensure_running(job)
    temporary = None
    try:
        if job.imagery.is_archived:
            raise _error("影像已归档，不能执行处理任务", "imagery_archived")
        directory = job_output_directory(job)
        directory.mkdir(parents=True, exist_ok=True)
        target = expected_output_path(job)
        temporary = (
            directory / f".{target.stem}.{uuid.uuid4().hex}.tmp{target.suffix}"
        ).resolve()
        if temporary.parent != directory.resolve() or temporary == target:
            raise _error("处理任务临时输出路径无效", "invalid_output")
        source = source_path_for_imagery(job.imagery)
        _run_raster_subprocess(job, source, temporary)
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise _error("栅格处理未生成有效结果文件", "missing_output")
        resolved_temporary = temporary.resolve(strict=True)
        if resolved_temporary.parent != directory.resolve(strict=True):
            raise _error("栅格处理结果超出任务目录", "invalid_output")
        os.replace(resolved_temporary, target)
        media_type = (
            "image/png"
            if job.output_format == ProcessingJob.OUTPUT_PNG
            else "image/tiff"
        )
        now = timezone.now()
        ProcessingJob.objects.filter(pk=job.pk).update(
            status=ProcessingJob.STATUS_SUCCEEDED,
            output_path=str(target),
            output_media_type=media_type,
            error_message="",
            finished_at=now,
            updated_at=now,
        )
        job.refresh_from_db()
        return target
    except Exception as exc:
        _mark_failed(job, exc)
        if isinstance(exc, ProcessingError):
            raise
        raise _error(f"栅格处理失败：{exc}", "processing_failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
            Path(f"{temporary}.aux.xml").unlink(missing_ok=True)


def claim_next_job():
    with transaction.atomic():
        job = (
            ProcessingJob.objects.select_for_update()
            .filter(status=ProcessingJob.STATUS_PENDING)
            .order_by("created_at")
            .first()
        )
        if not job:
            return None
        job.status = ProcessingJob.STATUS_RUNNING
        job.attempts += 1
        job.started_at = timezone.now()
        job.finished_at = None
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "attempts",
                "started_at",
                "finished_at",
                "error_message",
                "updated_at",
            ]
        )
        return job


def retry_job(job: ProcessingJob) -> ProcessingJob:
    with transaction.atomic():
        locked = (
            ProcessingJob.objects.select_for_update()
            .select_related("imagery")
            .get(pk=job.pk)
        )
        if locked.status != ProcessingJob.STATUS_FAILED:
            raise _error("仅失败任务可以重试", "invalid_status")
        if locked.imagery.is_archived:
            raise _error("影像已归档，不能重试处理任务", "imagery_archived")
        remove_job_outputs(locked)
        locked.status = ProcessingJob.STATUS_PENDING
        locked.output_path = ""
        locked.output_media_type = ""
        locked.error_message = ""
        locked.started_at = None
        locked.finished_at = None
        locked.save(
            update_fields=[
                "status",
                "output_path",
                "output_media_type",
                "error_message",
                "started_at",
                "finished_at",
                "updated_at",
            ]
        )
        return locked


def run_pending(limit=None):
    processed = 0
    while limit is None or processed < limit:
        job = claim_next_job()
        if not job:
            break
        try:
            process_job(job)
        except ProcessingError:
            pass
        processed += 1
    return processed
