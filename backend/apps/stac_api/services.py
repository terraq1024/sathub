import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings

from apps.imagery.models import ImageryAsset, ImageryRecord
from apps.imagery.stac import STAC_COLLECTION, build_stac_item_from_metadata
from apps.imagery.services import _metadata_from_record
from apps.access_control.authentication import has_scope
from apps.access_control.signing import build_signed_path


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _asset_href(request, image_id, role):
    # Catalog access must not implicitly grant asset access. Only a token with
    # the explicit assets/read scope receives an anonymous signed URL.
    if (
        request.auth is not None
        and request.META.get("HTTP_AUTHORIZATION", "").lower().startswith("bearer ")
        and has_scope(request.auth, "assets/read")
    ):
        expiry = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        return build_signed_path(request, image_id, role, expiry)
    return request.build_absolute_uri(f"/api/imagery/{image_id}/assets/{role}")


def _rewrite_item(item, request, imagery):
    item = dict(item)
    item["id"] = imagery.stac_id or imagery.scene_key
    item["collection"] = STAC_COLLECTION
    item["links"] = [
        {"rel": "self", "href": request.build_absolute_uri(f"/api/stac/collections/{STAC_COLLECTION}/items/{item['id']}")},
        {"rel": "collection", "href": request.build_absolute_uri(f"/api/stac/collections/{STAC_COLLECTION}")},
    ]
    assets = {}
    for asset in imagery.assets.all():
        value = dict((item.get("assets") or {}).get(asset.role, {}))
        value["href"] = _asset_href(request, str(imagery.pk), asset.role)
        value.setdefault("type", asset.media_type or None)
        assets[asset.role] = value
    item["assets"] = assets
    return item


def item_for_record(request, imagery):
    item = None
    if imagery.stac_path:
        try:
            item = json.loads(Path(imagery.stac_path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            item = None
    if not isinstance(item, dict):
        project_ids = [str(v) for v in imagery.project_tags.values_list("project_id", flat=True)]
        item = build_stac_item_from_metadata(
            scene_key=imagery.stac_id or imagery.scene_key,
            image_id=str(imagery.pk),
            metadata=_metadata_from_record(imagery),
            asset_hrefs={},
            project_ids=project_ids,
        )
    return _rewrite_item(item, request, imagery)


def collection(request):
    return {
        "type": "Collection",
        "stac_version": "1.0.0",
        "id": STAC_COLLECTION,
        "title": "Airmap 影像",
        "description": "Airmap 未归档卫星影像集合",
        "license": "proprietary",
        "extent": {"spatial": {"bbox": [[-180, -90, 180, 90]]}, "temporal": {"interval": [[None, None]]}},
        "links": [
            {"rel": "self", "href": request.build_absolute_uri(f"/api/stac/collections/{STAC_COLLECTION}")},
            {"rel": "items", "href": request.build_absolute_uri(f"/api/stac/collections/{STAC_COLLECTION}/items")},
        ],
    }


def parse_datetime(value):
    if value in (None, ""):
        return None, None
    parts = str(value).split("/")
    if len(parts) == 1:
        parts = [parts[0], parts[0]]
    if len(parts) != 2:
        raise ValueError("datetime must be an RFC3339 timestamp or interval")

    def parse(part):
        if part in ("", "..", "null", None):
            return None
        parsed = datetime.fromisoformat(part.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    return parse(parts[0]), parse(parts[1])


def parse_bbox(value):
    if value in (None, ""):
        return None
    try:
        values = [float(v) for v in (value if isinstance(value, list) else str(value).split(","))]
    except (TypeError, ValueError):
        raise ValueError("bbox must contain four numeric values")
    if len(values) not in (4, 6) or values[0] > values[2] or values[1] > values[3]:
        raise ValueError("bbox must contain four or six values in minx,miny,maxx,maxy order")
    return values[:4]


def normalize_ids(value):
    if value in (None, ""):
        return None
    values = value if isinstance(value, list) else str(value).split(",")
    return [str(v) for v in values if str(v)]


def _bbox_intersects(record_bbox, requested):
    if not requested:
        return True
    if not record_bbox or len(record_bbox) < 4:
        return False
    return not (record_bbox[2] < requested[0] or record_bbox[0] > requested[2] or record_bbox[3] < requested[1] or record_bbox[1] > requested[3])


def search_records(request, params):
    limit = int(params.get("limit", 10))
    if limit < 1 or limit > 10000:
        raise ValueError("limit must be between 1 and 10000")
    try:
        offset = int(params.get("offset", 0))
    except (TypeError, ValueError):
        raise ValueError("offset must be a non-negative integer")
    if offset < 0:
        raise ValueError("offset must be a non-negative integer")
    bbox = parse_bbox(params.get("bbox"))
    start, end = parse_datetime(params.get("datetime"))
    ids = normalize_ids(params.get("ids"))
    query = params.get("query") or {}
    allowed = {"platform_code", "satellite_name", "sensor", "imaging_mode", "polarization", "product_level"}
    if not isinstance(query, dict):
        raise ValueError("query must be an object")
    filters = {}
    for key, expression in query.items():
        if key not in allowed or not isinstance(expression, dict) or set(expression) != {"eq"}:
            raise ValueError("query supports only eq for known metadata fields")
        filters[key] = expression["eq"]
    qs = ImageryRecord.objects.filter(is_archived=False).prefetch_related("assets", "project_tags")
    if ids:
        qs = qs.filter(stac_id__in=ids) | qs.filter(scene_key__in=ids)
    for key, value in filters.items():
        qs = qs.filter(**{key: value})
    if start:
        qs = qs.filter(acquisition_end__gte=start) | qs.filter(acquisition_end__isnull=True, acquisition_time__gte=start)
    if end:
        qs = qs.filter(acquisition_start__lte=end) | qs.filter(acquisition_start__isnull=True, acquisition_time__lte=end)
    # OR branches used for nullable acquisition fallbacks can otherwise return
    # the same imagery more than once as the query grows.
    qs = qs.distinct()
    records = [record for record in qs.order_by("-acquisition_time", "-created_at") if _bbox_intersects(record.bbox, bbox)]
    return records, limit, offset


def next_search_link(request, params, offset):
    values = {}
    for key, value in params.items():
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        values[key] = value
    values["offset"] = offset
    return request.build_absolute_uri(request.path) + "?" + urlencode(values)
