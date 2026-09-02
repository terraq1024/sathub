from datetime import datetime, timezone
from pathlib import Path


STAC_COLLECTION = "sathub-imagery"
SAR_EXTENSION = "https://stac-extensions.github.io/sar/v1.0.0/schema.json"
PROJ_EXTENSION = "https://stac-extensions.github.io/projection/v1.1.0/schema.json"


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_stac_item_from_metadata(*, scene_key: str, image_id: str, metadata: dict, asset_hrefs: dict[str, str], project_ids: list[str] | None = None) -> dict:
    properties = {
        "datetime": _iso(metadata.get("acquisition_time")),
        "platform": metadata.get("platform_code"),
        "instruments": [metadata.get("sensor")] if metadata.get("sensor") else [],
        "processing:level": metadata.get("product_level"),
        "sar:polarizations": metadata.get("polarizations") or [],
        "sar:instrument_mode": metadata.get("imaging_mode"),
        "sar:observation_direction": metadata.get("look_side"),
        "sar:resolution_range": metadata.get("resolution_m"),
        "sar:resolution_azimuth": metadata.get("resolution_m"),
        "sar:pixel_spacing_range": metadata.get("pixel_spacing_range_m"),
        "sar:pixel_spacing_azimuth": metadata.get("pixel_spacing_azimuth_m"),
        "proj:epsg": metadata.get("epsg"),
        "proj:shape": [metadata.get("height"), metadata.get("width")] if metadata.get("height") and metadata.get("width") else None,
        "sathub:satellite_code": metadata.get("platform_code"),
        "sathub:satellite_name": metadata.get("satellite_name"),
        "sathub:sensor": metadata.get("sensor"),
        "sathub:polarization": metadata.get("polarization"),
        "sathub:polarization_raw": metadata.get("polarization_raw"),
        "sathub:imaging_mode_raw": metadata.get("imaging_mode_raw"),
        "sathub:imaging_mode_detail": metadata.get("imaging_mode_detail"),
        "sathub:imaging_mode_code": metadata.get("imaging_mode_code"),
        "sathub:acquisition_start": _iso(metadata.get("acquisition_start")),
        "sathub:acquisition_end": _iso(metadata.get("acquisition_end")),
        "sathub:time_assumption": metadata.get("time_assumption"),
        "sathub:orbit_id": metadata.get("orbit_id"),
        "sathub:orbit_direction": metadata.get("orbit_direction"),
        "sathub:incidence_angle_near_deg": metadata.get("incidence_angle_near_deg"),
        "sathub:incidence_angle_far_deg": metadata.get("incidence_angle_far_deg"),
        "sathub:resolution_m": metadata.get("resolution_m"),
        "sathub:metadata_status": metadata.get("metadata_status"),
        "sathub:spatial_status": metadata.get("spatial_status"),
        "sathub:preview_status": metadata.get("preview_status"),
        "sathub:preview_warp_bounds": metadata.get("preview_warp_bounds"),
        "sathub:cog_status": metadata.get("cog_status"),
        "sathub:source_name": metadata.get("source_name"),
        "sathub:display_name": metadata.get("display_name"),
        "sathub:description": metadata.get("description"),
        "sathub:is_archived": bool(metadata.get("is_archived")),
        "sathub:project_ids": project_ids or [],
    }
    properties = {key: value for key, value in properties.items() if value not in (None, [], "")}
    item_dict = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [SAR_EXTENSION, PROJ_EXTENSION],
        "id": scene_key,
        "collection": STAC_COLLECTION,
        "geometry": metadata.get("geometry"),
        "bbox": metadata.get("bbox"),
        "properties": properties,
        "links": [],
        "assets": {},
    }
    media_types = {
        "data": "image/tiff; application=geotiff",
        "preview": "image/jpeg",
        "thumbnail": "image/jpeg",
        "metadata": "application/xml",
        "incidence": "application/xml",
        "log": "text/plain",
    }
    roles = {
        "data": ["data"],
        "preview": ["thumbnail", "overview"],
        "thumbnail": ["thumbnail"],
        "metadata": ["metadata"],
        "incidence": ["metadata"],
        "log": ["metadata"],
    }
    for role, href in asset_hrefs.items():
        item_dict["assets"][role] = {
            "href": href,
            "type": media_types.get(role),
            "roles": roles.get(role, []),
        }
    try:
        import pystac

        item_dict = pystac.Item.from_dict(item_dict).to_dict()
        item_dict["stac_version"] = "1.0.0"
        item_dict["collection"] = STAC_COLLECTION
    except Exception:
        # Partial metadata is still persisted for later repair; the API exposes the status.
        pass
    return item_dict


def build_stac_item(*, stac_id: str, project_id: str | None, raw_path: str, parsed, raster: dict) -> dict:
    metadata = {
        "source_name": parsed.source_name,
        "platform_code": parsed.platform,
        "product_level": parsed.product_level,
        "polarization": parsed.polarization,
        "polarizations": [parsed.polarization] if parsed.polarization else [],
        "acquisition_time": parsed.acquisition_time,
        "geometry": raster.get("geometry"),
        "bbox": raster.get("bbox"),
        "epsg": raster.get("epsg"),
        "spatial_status": raster.get("spatial_status", "partial"),
        "metadata_status": "partial",
        "time_assumption": parsed.time_assumption,
        "imaging_mode_raw": parsed.mode_code,
    }
    return build_stac_item_from_metadata(
        scene_key=stac_id,
        image_id=stac_id,
        metadata=metadata,
        asset_hrefs={"data": Path(raw_path).resolve().as_uri()},
        project_ids=[str(project_id)] if project_id else [],
    )
