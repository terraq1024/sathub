from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import QuerySet

from .models import (
    DatasetClassification,
    DatasetTag,
    ImageryAdministrativeUnit,
    ImageryClassification,
    ImageryTag,
)


def geometry_bbox(geometry: dict[str, Any]) -> list[float]:
    points = []
    if geometry.get("type") == "Polygon":
        rings = geometry.get("coordinates", [])
    elif geometry.get("type") == "MultiPolygon":
        rings = [ring for polygon in geometry.get("coordinates", []) for ring in polygon]
    else:
        raise ValueError("Only Polygon and MultiPolygon geometries are supported")
    for ring in rings:
        for point in ring:
            if len(point) >= 2:
                points.append((float(point[0]), float(point[1])))
    if not points:
        raise ValueError("Geometry has no coordinates")
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def _rings(geometry):
    if geometry.get("type") == "Polygon":
        return geometry.get("coordinates", [])
    return [ring for polygon in geometry.get("coordinates", []) for ring in polygon]


def geometry_center(geometry):
    bbox = geometry_bbox(geometry)
    return [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]


def point_in_ring(point, ring):
    inside = False
    x, y = point[:2]
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        if ((start[1] > y) != (end[1] > y)) and x < (end[0] - start[0]) * (y - start[1]) / (end[1] - start[1]) + start[0]:
            inside = not inside
    return inside


def point_in_geometry(point, geometry):
    return any(point_in_ring(point, ring) for ring in _rings(geometry) if len(ring) >= 3)


def normalize_gb_code(value: Any, *, fallback_name: str = "") -> str:
    """Return the platform's canonical 156 + six digit GB code."""
    import hashlib

    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("156"):
        digits = digits[3:]
    if len(digits) > 6:
        digits = digits[-6:]
    if len(digits) < 6:
        if not fallback_name:
            raise ValueError("Administrative unit is missing gb code")
        digest = hashlib.sha256(fallback_name.encode("utf-8")).hexdigest()
        digits = (digits + str(int(digest[:12], 16) % 1_000_000).zfill(6))[:6]
    return f"156{digits.zfill(6)}"


def raw_gb_code(code: str) -> str:
    return code[3:] if code.startswith("156") and len(code) == 9 else code


def derived_parent_code(code: str, level: str) -> str | None:
    raw = raw_gb_code(code)
    if len(raw) != 6:
        return None
    if level == "city":
        return normalize_gb_code(raw[:2] + "0000")
    if level == "county":
        return normalize_gb_code(raw[:4] + "00")
    return None


def _ids(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


def imagery_ids_for_filters(
    *,
    administrative_unit_ids: Iterable[Any] = (),
    classification_ids: Iterable[Any] = (),
    tag_ids: Iterable[Any] = (),
    include_archived: bool = False,
) -> QuerySet:
    """Return an ImageryRecord queryset without importing or mutating its app."""
    from apps.imagery.models import ImageryRecord

    queryset = ImageryRecord.objects.all()
    if not include_archived:
        queryset = queryset.filter(is_archived=False)
    admin_ids = _ids(administrative_unit_ids)
    class_ids = _ids(classification_ids)
    tags = _ids(tag_ids)
    if admin_ids:
        queryset = queryset.filter(administrative_units__administrative_unit_id__in=admin_ids)
    if class_ids:
        queryset = queryset.filter(classifications__classification_id__in=class_ids)
    if tags:
        queryset = queryset.filter(catalog_tags__tag_id__in=tags)
    return queryset.distinct().values_list("id", flat=True)


def dataset_ids_for_filters(*, classification_ids=(), tag_ids=()):
    from apps.imagery.models import ImageryDataset

    queryset = ImageryDataset.objects.filter(status=ImageryDataset.STATUS_ACTIVE)
    if classification_ids:
        queryset = queryset.filter(classifications__classification_id__in=_ids(classification_ids))
    if tag_ids:
        queryset = queryset.filter(catalog_tags__tag_id__in=_ids(tag_ids))
    return queryset.distinct().values_list("id", flat=True)


def query_imagery_ids(**filters):
    """Compatibility alias for callers that prefer an explicit query name."""
    return imagery_ids_for_filters(**filters)


def link_imagery(*, imagery_ids, classification_ids=(), tag_ids=(), user=None, replace=False):
    from apps.imagery.models import ImageryRecord

    images = list(ImageryRecord.objects.filter(pk__in=_ids(imagery_ids)))
    if len(images) != len(_ids(imagery_ids)):
        raise ValueError("One or more imagery IDs do not exist")
    if replace:
        ImageryClassification.objects.filter(imagery_id__in=[image.pk for image in images]).delete()
        ImageryTag.objects.filter(imagery_id__in=[image.pk for image in images]).delete()
    class_links = [ImageryClassification(imagery=image, classification_id=classification_id, created_by=user) for image in images for classification_id in _ids(classification_ids)]
    tag_links = [ImageryTag(imagery=image, tag_id=tag_id, created_by=user) for image in images for tag_id in _ids(tag_ids)]
    ImageryClassification.objects.bulk_create(class_links, ignore_conflicts=True)
    ImageryTag.objects.bulk_create(tag_links, ignore_conflicts=True)


def link_datasets(*, dataset_ids, classification_ids=(), tag_ids=(), user=None, replace=False):
    from apps.imagery.models import ImageryDataset

    datasets = list(ImageryDataset.objects.filter(pk__in=_ids(dataset_ids)))
    if len(datasets) != len(_ids(dataset_ids)):
        raise ValueError("One or more dataset IDs do not exist")
    if replace:
        DatasetClassification.objects.filter(dataset_id__in=[dataset.pk for dataset in datasets]).delete()
        DatasetTag.objects.filter(dataset_id__in=[dataset.pk for dataset in datasets]).delete()
    class_links = [DatasetClassification(dataset=dataset, classification_id=classification_id, created_by=user) for dataset in datasets for classification_id in _ids(classification_ids)]
    tag_links = [DatasetTag(dataset=dataset, tag_id=tag_id, created_by=user) for dataset in datasets for tag_id in _ids(tag_ids)]
    DatasetClassification.objects.bulk_create(class_links, ignore_conflicts=True)
    DatasetTag.objects.bulk_create(tag_links, ignore_conflicts=True)
