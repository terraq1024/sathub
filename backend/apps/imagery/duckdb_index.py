import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS imagery_index (
    image_id VARCHAR PRIMARY KEY,
    stac_id VARCHAR NOT NULL,
    collection_id VARCHAR,
    scene_key VARCHAR,
    project_id VARCHAR,
    project_ids VARCHAR,
    owner_id VARCHAR,
    job_id VARCHAR,
    item_id VARCHAR,
    source_name VARCHAR,
    display_name VARCHAR,
    description VARCHAR,
    file_path VARCHAR,
    raw_path VARCHAR,
    preview_path VARCHAR,
    cog_path VARCHAR,
    thumbnail_path VARCHAR,
    platform VARCHAR,
    source_vendor VARCHAR,
    satellite_name VARCHAR,
    sensor VARCHAR,
    imaging_mode VARCHAR,
    imaging_mode_detail VARCHAR,
    product_level VARCHAR,
    polarization VARCHAR,
    polarizations JSON,
    resolution_m DOUBLE,
    pixel_spacing_range_m DOUBLE,
    pixel_spacing_azimuth_m DOUBLE,
    acquisition_time TIMESTAMP,
    acquisition_start TIMESTAMP,
    acquisition_end TIMESTAMP,
    center_lon DOUBLE,
    center_lat DOUBLE,
    min_lon DOUBLE,
    min_lat DOUBLE,
    max_lon DOUBLE,
    max_lat DOUBLE,
    epsg INTEGER,
    spatial_status VARCHAR,
    metadata_status VARCHAR,
    preview_status VARCHAR,
    cog_status VARCHAR,
    visibility VARCHAR,
    asset_access_modes JSON,
    footprint_geojson JSON,
    stac_path VARCHAR,
    status VARCHAR NOT NULL,
    is_archived BOOLEAN,
    archived_at TIMESTAMP,
    archived_by_id VARCHAR,
    stac_json JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
"""


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise ImproperlyConfigured("duckdb is required. Install backend/requirements.txt before running imagery indexing.") from exc
    return duckdb


def _connect():
    db_path = Path(settings.DUCKDB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _duckdb().connect(str(db_path))
    conn.execute(SCHEMA_SQL)
    _ensure_columns(conn)
    return conn


def _ensure_columns(conn, record: dict | None = None):
    existing = {row[0] for row in conn.execute("DESCRIBE imagery_index").fetchall()}
    type_map = {
        "scene_key": "VARCHAR", "project_ids": "VARCHAR", "satellite_name": "VARCHAR",
        "source_vendor": "VARCHAR",
        "preview_path": "VARCHAR", "imaging_mode": "VARCHAR", "imaging_mode_detail": "VARCHAR",
        "polarizations": "JSON", "resolution_m": "DOUBLE", "pixel_spacing_range_m": "DOUBLE",
        "pixel_spacing_azimuth_m": "DOUBLE", "acquisition_start": "TIMESTAMP", "acquisition_end": "TIMESTAMP",
        "metadata_status": "VARCHAR", "preview_status": "VARCHAR", "cog_status": "VARCHAR", "visibility": "VARCHAR", "asset_access_modes": "JSON", "footprint_geojson": "JSON", "stac_path": "VARCHAR",
        "display_name": "VARCHAR", "description": "VARCHAR", "is_archived": "BOOLEAN",
        "archived_at": "TIMESTAMP", "archived_by_id": "VARCHAR",
    }
    for column, sql_type in type_map.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE imagery_index ADD COLUMN {column} {sql_type}")


def upsert_image(record: dict) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    record = {**record, "updated_at": now}
    record.setdefault("created_at", now)
    record.setdefault("display_name", "")
    record.setdefault("description", "")
    record.setdefault("is_archived", False)
    columns = [
        "image_id", "stac_id", "collection_id", "scene_key", "project_id", "project_ids", "owner_id", "job_id", "item_id",
        "source_name", "display_name", "description", "file_path", "raw_path", "preview_path", "cog_path", "thumbnail_path", "platform", "source_vendor", "satellite_name",
        "sensor", "imaging_mode", "imaging_mode_detail", "product_level", "polarization", "polarizations", "resolution_m",
        "pixel_spacing_range_m", "pixel_spacing_azimuth_m", "acquisition_time", "acquisition_start", "acquisition_end",
        "center_lon", "center_lat", "min_lon", "min_lat", "max_lon", "max_lat", "epsg", "spatial_status", "metadata_status",
        "preview_status", "cog_status", "visibility", "asset_access_modes", "footprint_geojson", "stac_path", "status", "is_archived", "archived_at", "archived_by_id",
        "stac_json", "created_at", "updated_at",
    ]
    record.setdefault("source_vendor", _source_vendor(
        record.get("platform") or record.get("platform_code"),
        record.get("satellite_name"),
        record.get("source_name"),
    ))
    values = [record.get(column) for column in columns]
    for field in ("polarizations", "footprint_geojson", "stac_json"):
        values[columns.index(field)] = json.dumps(record.get(field) or ([] if field == "polarizations" else {}), ensure_ascii=False)
    placeholders = ", ".join(["?"] * len(columns))
    assignments = ", ".join([f"{column}=excluded.{column}" for column in columns if column != "image_id"])
    with _connect() as conn:
        _ensure_columns(conn, record)
        conn.execute(
            f"INSERT INTO imagery_index ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT(image_id) DO UPDATE SET {assignments}",
            values,
        )


def search_images(*, user, filters: dict, page: int = 1, page_size: int = 50) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    clauses, params = [], []
    if "image_ids" in filters:
        image_ids = list(dict.fromkeys(str(value) for value in (filters.get("image_ids") or [])))
        if not image_ids:
            return {"count": 0, "page": page, "page_size": page_size, "results": []}
        placeholders = ", ".join(["?"] * len(image_ids))
        clauses.append(f"image_id IN ({placeholders})")
        params.extend(image_ids)
    if filters.get("include_archived"):
        if not user.is_staff:
            clauses.append("(COALESCE(is_archived, FALSE) = FALSE OR owner_id = ?)")
            params.append(str(user.pk))
    else:
        clauses.append("COALESCE(is_archived, FALSE) = FALSE")
    # Visibility: public imagery for everyone; private only for its owner
    # and staff.
    if user.is_staff:
        pass
    else:
        clauses.append("(COALESCE(visibility, 'public') = 'public' OR owner_id = ?)")
        params.append(str(user.pk))
    exact_fields = ["platform", "source_vendor", "satellite_name", "sensor", "imaging_mode", "product_level", "polarization", "metadata_status", "preview_status", "cog_status"]
    for key in exact_fields:
        if filters.get(key):
            clauses.append(f"{key} = ?")
            params.append(str(filters[key]))
    if filters.get("sensor_type") == "sar":
        clauses.append("sensor ILIKE '%SAR%'")
    elif filters.get("sensor_type") == "optical":
        clauses.append("(sensor IS NOT NULL AND sensor <> '' AND sensor NOT ILIKE '%SAR%')")
    if filters.get("source_vendor"):
        clauses.append("source_vendor = ?")
        params.append(str(filters["source_vendor"]))
    if filters.get("project_id"):
        clauses.append("('|' || COALESCE(project_ids, '') || '|') LIKE ?")
        params.append(f"%|{filters['project_id']}|%")
    if filters.get("resolution_min") is not None:
        clauses.append("resolution_m >= ?")
        params.append(filters["resolution_min"])
    if filters.get("resolution_max") is not None:
        clauses.append("resolution_m <= ?")
        params.append(filters["resolution_max"])
    if filters.get("time_start"):
        clauses.append("acquisition_time >= ?")
        params.append(filters["time_start"])
    if filters.get("time_end"):
        clauses.append("acquisition_time <= ?")
        params.append(filters["time_end"])
    geometry = filters.get("geometry")
    spatial_bbox = filters.get("bbox")
    if geometry:
        from .spatial import _bbox
        spatial_bbox = _bbox(geometry)
    if spatial_bbox:
        min_lon, min_lat, max_lon, max_lat = spatial_bbox
        clauses.append("(min_lon <= ? AND max_lon >= ? AND min_lat <= ? AND max_lat >= ?)")
        params.extend([max_lon, min_lon, max_lat, min_lat])
    if filters.get("q"):
        needle = f"%{filters['q']}%"
        clauses.append("(source_name ILIKE ? OR display_name ILIKE ? OR description ILIKE ? OR stac_id ILIKE ? OR scene_key ILIKE ? OR satellite_name ILIKE ? OR imaging_mode ILIKE ?)")
        params.extend([needle] * 7)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    offset = (page - 1) * page_size
    with _connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM imagery_index{where_sql}", params).fetchone()[0]
        cursor = conn.execute(f"SELECT * FROM imagery_index{where_sql} ORDER BY acquisition_time DESC NULLS LAST, created_at DESC LIMIT ? OFFSET ?", [*params, page_size, offset])
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    results = [_row_to_dict(columns, row) for row in rows]
    if geometry:
        from .spatial import geometries_relation
        results = [result for result in results if result.get("geometry") and geometries_relation(result["geometry"], geometry, filters.get("spatial_relation", "intersects"))]
        # Exact geometry filtering must also correct total and pagination after bbox prefilter.
        if len(results) < len(rows) or total:
            with _connect() as conn:
                all_rows = conn.execute(f"SELECT * FROM imagery_index{where_sql} ORDER BY acquisition_time DESC NULLS LAST, created_at DESC", params).fetchall()
                all_results = [_row_to_dict(columns, row) for row in all_rows]
            total = sum(1 for result in all_results if result.get("geometry") and geometries_relation(result["geometry"], geometry, filters.get("spatial_relation", "intersects")))
            results = [result for result in all_results if result.get("geometry") and geometries_relation(result["geometry"], geometry, filters.get("spatial_relation", "intersects"))][offset:offset + page_size]
    for result in results:
        result["can_manage"] = bool(user.is_staff or str(result.get("owner_id")) == str(user.pk))
    return {"count": total, "page": page, "page_size": page_size, "results": results}


def _source_vendor(platform: str, satellite: str, source_name: str) -> str:
    values = [str(value or "").strip() for value in (platform, satellite, source_name)]
    text = " ".join(values).upper()
    vendor_rules = [
        ("UMBRA", "Umbra"),
        ("CAPELLA", "Capella Space"),
        ("ICEYE", "ICEYE"),
        ("AIRSAT", "AIRSAT"),
        ("SENTINEL", "Sentinel"),
        ("LANDSAT", "Landsat"),
        ("WORLDVIEW", "WorldView"),
        ("PLANET", "Planet"),
        ("高分", "高分"),
    ]
    for marker, label in vendor_rules:
        if marker in text:
            return label
    platform_text = values[0].upper()
    satellite_text = values[1].upper()
    if platform_text == "AS" or platform_text.startswith("AS") and platform_text[2:].isdigit():
        return "AIRSAT"
    for candidate in (platform_text, satellite_text):
        if candidate:
            token = candidate.replace("\\", "/").replace("_", "-").split("/")[-1].split("-")[0].strip()
            if token and not token.isdigit():
                return token
    return "未识别厂商"


def imagery_facets(*, user) -> dict:
    clauses = ["COALESCE(is_archived, FALSE) = FALSE"]
    where_sql = " WHERE " + " AND ".join(clauses)
    params = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT platform, satellite_name, source_name, COUNT(*) AS count "
            f"FROM imagery_index{where_sql} "
            "AND (COALESCE(platform, '') <> '' OR COALESCE(satellite_name, '') <> '') "
            "GROUP BY platform, satellite_name, source_name "
            "ORDER BY count DESC, platform, satellite_name",
            params,
        ).fetchall()
        value_rows = conn.execute(
            "SELECT sensor, imaging_mode, product_level, polarization, COUNT(*) AS count "
            f"FROM imagery_index{where_sql} GROUP BY sensor, imaging_mode, product_level, polarization",
            params,
        ).fetchall()

    satellites = {}
    vendors = {}
    value_sets = {"sensors": {}, "imaging_modes": {}, "product_levels": {}, "polarizations": {}}
    for platform, satellite, source_name, count in rows:
        platform = str(platform or "").strip()
        satellite = str(satellite or "").strip()
        source_name = str(source_name or "").strip()
        vendor = _source_vendor(platform, satellite, source_name)
        if satellite:
            item = satellites.setdefault(satellite, {"value": satellite, "label": satellite, "count": 0})
            item["count"] += int(count)
        if vendor:
            item = vendors.setdefault(vendor, {"value": vendor, "label": vendor, "count": 0})
            item["count"] += int(count)
    for sensor, imaging_mode, product_level, polarization, count in value_rows:
        for key, value in (("sensors", sensor), ("imaging_modes", imaging_mode), ("product_levels", product_level), ("polarizations", polarization)):
            value = str(value or "").strip()
            if value:
                item = value_sets[key].setdefault(value, {"value": value, "label": value, "count": 0})
                item["count"] += int(count)
    return {
        "satellites": sorted(satellites.values(), key=lambda item: (-item["count"], item["label"])),
        "vendors": sorted(vendors.values(), key=lambda item: (-item["count"], item["label"])),
        **{key: sorted(values.values(), key=lambda item: (-item["count"], item["label"])) for key, values in value_sets.items()},
    }


def get_image(*, user, image_id: str, include_archived: bool = False) -> dict | None:
    with _connect() as conn:
        params = [image_id]
        if include_archived and user.is_staff:
            archived_clause = ""
        elif include_archived:
            archived_clause = " AND (COALESCE(is_archived, FALSE) = FALSE OR owner_id = ?)"
            params.append(str(user.pk))
        else:
            archived_clause = " AND COALESCE(is_archived, FALSE) = FALSE"
        if not user.is_staff:
            archived_clause += " AND (COALESCE(visibility, 'public') = 'public' OR owner_id = ?)"
            params.append(str(user.pk))
        cursor = conn.execute(f"SELECT * FROM imagery_index WHERE image_id = ?{archived_clause}", params)
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
    result = _row_to_dict(columns, row)
    result["can_manage"] = bool(user.is_staff or str(result.get("owner_id")) == str(user.pk))
    return result


def update_project_ids(image_id: str, project_ids: list[str]) -> None:
    # Compatibility entry point used by ingestion. Rebuild the complete
    # projection so project changes also reach STAC and newer index fields.
    from .models import ImageryRecord
    from .services import sync_imagery_projection

    if ImageryRecord.objects.filter(pk=image_id).exists():
        sync_imagery_projection(image_id)
        return
    with _connect() as conn:
        conn.execute(
            "UPDATE imagery_index SET project_ids = ?, updated_at = ? WHERE image_id = ?",
            ["|".join(sorted(set(project_ids))), datetime.now(timezone.utc).replace(tzinfo=None), image_id],
        )


def clear_index() -> None:
    with _connect() as conn:
        _ensure_columns(conn)
        conn.execute("DELETE FROM imagery_index")


def delete_image(image_id: str) -> None:
    with _connect() as conn:
        _ensure_columns(conn)
        conn.execute("DELETE FROM imagery_index WHERE image_id = ?", [image_id])


def _row_to_dict(columns, row):
    data = dict(zip(columns, row))
    for field in ("stac_json", "footprint_geojson", "polarizations"):
        if isinstance(data.get(field), str):
            try:
                data[field] = json.loads(data[field])
            except json.JSONDecodeError:
                pass
    data["geometry"] = data.get("footprint_geojson")
    data["effective_display_name"] = data.get("display_name") or data.get("source_name")
    return data
