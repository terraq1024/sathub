"""AIRSAT product parsing: filename convention and meta.xml metadata.

This module is the single home of AIRSAT-specific parsing. The OSS edition
ships without it; apps.imagery.metadata degrades to generic raster, STAC and
vendor-JSON metadata when the import fails.
"""

import re
from datetime import datetime

from .metadata import LOCAL_TZ, ParsedFilename, UTC, _parse_datetime, _polarizations, _source_stem

FILENAME_PATTERN = re.compile(
    r"^(?P<platform>[A-Z0-9]+)_(?P<mode>[A-Z0-9]+)_(?P<direction>[A-Z0-9]+)_"
    r"(?P<scene_id>\d+)_(?P<lon>[EW]\d+(?:\.\d+)?)_(?P<lat>[NS]\d+(?:\.\d+)?)_"
    r"(?P<datetime>\d{14})_(?P<level>L\d+)_(?P<polarization>[A-Z]{2})_"
    r"(?P<version>\d+)_(?P<sequence>\d+)$"
)


def _parse_coord(value: str) -> float:
    return (-1 if value[0] in {"W", "S"} else 1) * float(value[1:])


def parse_source_name(path_or_name: str) -> ParsedFilename:
    from pathlib import Path

    source_name = _source_stem(path_or_name)
    match = FILENAME_PATTERN.match(source_name)
    if not match:
        return ParsedFilename(source_name=source_name)
    groups = match.groupdict()
    local_dt = datetime.strptime(groups["datetime"], "%Y%m%d%H%M%S").replace(tzinfo=LOCAL_TZ)
    return ParsedFilename(
        source_name=source_name,
        platform=groups["platform"],
        mode_code=groups["mode"],
        direction_code=groups["direction"],
        scene_id=groups["scene_id"],
        center_lon=_parse_coord(groups["lon"]),
        center_lat=_parse_coord(groups["lat"]),
        acquisition_time=local_dt.astimezone(UTC),
        product_level=groups["level"],
        polarization=groups["polarization"],
        version=groups["version"],
        sequence=groups["sequence"],
    )


def _xml_root(path):
    from lxml import etree

    raw = path.read_bytes()
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True)
    try:
        return etree.fromstring(raw, parser=parser)
    except (etree.XMLSyntaxError, UnicodeDecodeError):
        return etree.fromstring(raw.decode("gb18030", errors="replace").encode("utf-8"), parser=parser)


def _xml_text(root, path: str) -> str | None:
    expression = "/" + "/".join(f"*[local-name()='{part}']" for part in path.split("/"))
    nodes = root.xpath(expression) or root.xpath("//" + "/".join(f"*[local-name()='{part}']" for part in path.split("/")))
    if not nodes or nodes[0].text is None:
        return None
    return nodes[0].text.strip()


def _xml_float(root, path: str) -> float | None:
    value = _xml_text(root, path)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _xml_int(root, path: str) -> int | None:
    value = _xml_text(root, path)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _footprint(root) -> tuple[dict | None, list[float] | None]:
    coordinates = []
    for name in ("topLeft", "topRight", "bottomRight", "bottomLeft"):
        lon = _xml_float(root, f"imageinfo/corner/{name}/Longitude")
        lat = _xml_float(root, f"imageinfo/corner/{name}/Latitude")
        if lon is None or lat is None:
            return None, None
        coordinates.append([lon, lat])
    coordinates.append(coordinates[0])
    bbox = [min(point[0] for point in coordinates), min(point[1] for point in coordinates), max(point[0] for point in coordinates), max(point[1] for point in coordinates)]
    return {"type": "Polygon", "coordinates": [coordinates]}, bbox


def parse_meta_xml_values(group, parsed: ParsedFilename) -> dict:
    """Parse an AIRSAT meta.xml sidecar into the shared metadata value dict."""
    root = _xml_root(group.metadata_path)
    polar_raw = _xml_text(root, "sensor/polarParams/polar/polarMode") or _xml_text(root, "productinfo/productPolar")
    values = {
        "platform_code": parsed.platform or (_xml_text(root, "Productid") or "").split("_")[0] or None,
        "satellite_name": _xml_text(root, "satellite"),
        "sensor": _xml_text(root, "sensor/sensorID"),
        "imaging_mode": _xml_text(root, "productinfo/productType") or _xml_text(root, "sensor/imagingMode"),
        "imaging_mode_raw": _xml_text(root, "sensor/imagingMode"),
        "polarizations": _polarizations(polar_raw) or (list(parsed.polarizations) if parsed.polarizations else []),
        "polarization_raw": polar_raw,
        "product_level": _xml_text(root, "productinfo/productLevel") or parsed.product_level,
        "acquisition_start": _parse_datetime(_xml_text(root, "imageinfo/imagingTime/start")),
        "acquisition_end": _parse_datetime(_xml_text(root, "imageinfo/imagingTime/end")),
        "orbit_id": _xml_text(root, "orbitID"),
        "orbit_direction": _xml_text(root, "Direction"),
        "look_side": _xml_text(root, "LookSide"),
        "resolution_m": _xml_float(root, "productinfo/NominalResolution"),
        "pixel_spacing_range_m": _xml_float(root, "imageinfo/Widthspace"),
        "pixel_spacing_azimuth_m": _xml_float(root, "imageinfo/Heightspace"),
        "width": _xml_int(root, "imageinfo/Width"),
        "height": _xml_int(root, "imageinfo/Height"),
        "incidence_angle_near_deg": _xml_float(root, "processinfo/incidenceAngleNearRange"),
        "incidence_angle_far_deg": _xml_float(root, "processinfo/incidenceAngleFarRange"),
        "polarization": parsed.polarization,
    }
    center_time = _parse_datetime(_xml_text(root, "platform/CenterTime"))
    receive_time = _parse_datetime(_xml_text(root, "ReceiveTime"))
    values["acquisition_time"] = center_time or parsed.acquisition_time or receive_time
    values["metadata_sources"] = ["filename", "meta.xml"]
    values["metadata_status"] = "ready"
    values["raw_metadata"] = {"product_id": _xml_text(root, "Productid"), "receive_time": _xml_text(root, "ReceiveTime"), "center_time": _xml_text(root, "platform/CenterTime"), "polarization_raw": polar_raw}
    geometry, bbox = _footprint(root)
    if geometry:
        values["geometry"], values["bbox"] = geometry, bbox
        values["spatial_status"] = "ready"
    return values
