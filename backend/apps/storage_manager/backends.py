"""Storage backends. All object access uses endpoint-relative keys."""

from __future__ import annotations

import fnmatch
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from django.conf import settings

from .models import StorageEndpoint


class StorageBackendError(Exception):
    pass


class UnsupportedStorageBackend(StorageBackendError):
    pass


@dataclass(frozen=True)
class StorageEntry:
    object_key: str
    size_bytes: int
    modified_at: datetime
    fingerprint: str


def _configured_allowed_roots():
    roots = getattr(settings, "STORAGE_ALLOWED_ROOTS", [])
    return [Path(root).expanduser().resolve() for root in roots]


def validate_local_root(root_uri: str) -> Path:
    if not isinstance(root_uri, str) or not root_uri.strip():
        raise StorageBackendError("存储根目录不能为空。")
    candidate = Path(root_uri).expanduser()
    if not candidate.is_absolute():
        raise StorageBackendError("存储根目录必须是绝对路径或 UNC 路径。")
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise StorageBackendError("存储根目录不存在或当前服务进程无法访问。") from exc
    if not resolved.is_dir():
        raise StorageBackendError("存储根目录必须是目录。")
    allowed = _configured_allowed_roots()
    if allowed and not any(resolved == root or root in resolved.parents for root in allowed):
        raise StorageBackendError("存储根目录不在管理员允许的路径范围内。")
    return resolved


def validate_prefix(prefix: str) -> str:
    prefix = (prefix or "").replace("\\", "/").strip("/")
    if prefix and ("\x00" in prefix or any(part in {"", ".", ".."} for part in prefix.split("/"))):
        raise StorageBackendError("扫描范围必须是存储根目录下的相对路径。")
    return prefix


def validate_object_key(object_key: str) -> str:
    key = (object_key or "").replace("\\", "/")
    if not key or key.startswith("/") or "\x00" in key or re.match(r"^[A-Za-z]:/", key):
        raise StorageBackendError("object_key 必须是非空相对路径。")
    if any(part in {"", ".", ".."} for part in key.split("/")):
        raise StorageBackendError("object_key 不允许绝对路径或路径穿越。")
    return key


class StorageBackend(ABC):
    def __init__(self, endpoint: StorageEndpoint):
        self.endpoint = endpoint

    @abstractmethod
    def check(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def iter_objects(self, prefix: str = "") -> Iterator[StorageEntry]:
        raise NotImplementedError


class LocalDirectoryBackend(StorageBackend):
    def __init__(self, endpoint: StorageEndpoint):
        super().__init__(endpoint)
        self.root = validate_local_root(endpoint.root_uri)

    def check(self) -> None:
        if not os.access(self.root, os.R_OK):
            raise StorageBackendError("存储根目录不可读。")

    def _matches_policy(self, key: str) -> bool:
        policy = self.endpoint.scan_policy or {}
        include = policy.get("include") or [
            "*.tif", "*.tiff", "*.jp2", "*.jpg", "*.jpeg", "*.nitf", "*.cphd", "*.xml", "*.json", "*.log",
        ]
        exclude = policy.get("exclude") or []
        included = any(fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(Path(key).name, pattern) for pattern in include)
        excluded = any(fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(Path(key).name, pattern) for pattern in exclude)
        return included and not excluded

    def iter_objects(self, prefix: str = "") -> Iterator[StorageEntry]:
        prefix = validate_prefix(prefix)
        base = (self.root / prefix).resolve()
        if base != self.root and self.root not in base.parents:
            raise StorageBackendError("扫描范围超出存储根目录。")
        if not base.exists() or not base.is_dir():
            raise StorageBackendError("扫描范围不存在或不是目录。")
        for current, directories, filenames in os.walk(base, followlinks=False):
            directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
            for name in sorted(filenames):
                path = Path(current) / name
                if path.is_symlink():
                    continue
                key = str(path.relative_to(self.root)).replace("\\", "/")
                if not self._matches_policy(key):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                yield StorageEntry(
                    object_key=validate_object_key(key),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    fingerprint=f"{stat.st_size}:{stat.st_mtime_ns}",
                )


def get_backend(endpoint: StorageEndpoint) -> StorageBackend:
    if endpoint.endpoint_type in {StorageEndpoint.TYPE_LOCAL, StorageEndpoint.TYPE_NAS}:
        return LocalDirectoryBackend(endpoint)
    raise UnsupportedStorageBackend("当前版本暂不支持 S3、SFTP 和 FTP 扫描。")
