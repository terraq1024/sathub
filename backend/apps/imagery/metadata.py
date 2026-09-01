import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")
IMAGE_EXTENSIONS = {".tif", ".tiff", ".jp2", ".vrt", ".img"}
UMBRA_AUXILIARY_EXTENSIONS = {".nitf", ".cphd"}


@dataclass
class ParsedFilename:
    source_name: str
    platform: str | None = None
    mode_code: str | None = None
    direction_code: str | None = None
    scene_id: str | None = None
    acquisition_time: datetime | None = None
    product_level: str | None = None
    polarization: str | None = None
    version: str | None = None
    sequence: str | None = None
    center_lon: float | None = None
    center_lat: float | None = None
    metadata_source: str = "filename"
    time_assumption: str = "Asia/Shanghai"


@dataclass
class ProductGroup:
    stem: str
    files: dict[str, Path] = field(default_factory=dict)

    @property
    def data_path(self) -> Path | None:
        for extension in (".tiff", ".tif", ".jp2", ".vrt", ".img"):
            if self.files.get(extension):
                return self.files[extension]
        return None

    @property
    def metadata_path(self) -> Path | None:
        if self.files.get("meta.xml"):
            return self.files["meta.xml"]
        # Vendor scenes carry several product metadata jsons (CSI/GRD/SLC);
        # prefer the highest-priority product across both json buckets.
        candidates = [self.files[b] for b in ("metadata.json", "stac.json") if self.files.get(b)]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda path: _product_rank(path.name.lower(), METADATA_PRODUCT_PRIORITY),
        )

    @property
    def preview_path(self) -> Path | None:
        return self.files.get("preview.jpg") or self.files.get("preview.png")


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def _source_stem(path_or_name: str | Path) -> str:
    name = Path(path_or_name).name
    lowered = name.lower()
    for suffix in (".meta.incidence.xml", ".meta.xml", ".result.xml", ".tiff.aux.xml", ".thumb.jpg", ".thumb.jpeg", ".thumb.png", "_extended.json.json", ".stac.v2.json"):
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    for suffix in (".tiff", ".tif", ".jp2", ".vrt", ".img", ".jpg", ".jpeg", ".png", ".json", ".log"):
        if lowered.endswith(suffix):
            # Vendor packages keep several product files for one scene in a
            # directory (``_GEC.tif`` + ``_CPHD.cphd`` + ``_METADATA.json``);
            # they share one stem once the product suffix is stripped.
            return re.sub(
                r"_(?:GEC|GEO|SICD(?:_MM)?|SIDD(?:_MM)?|CPHD|MM"
                r"|GRD|SLC|QLK|THM|METADATA|EXTENDED|PREVIEW|THUMB)$",
                "",
                name[: -len(suffix)],
                flags=re.IGNORECASE,
            )
    return name


def _airsat_module():
    """Load the AIRSAT parser when the edition bundles it (enterprise only)."""
    try:
        from apps.imagery import airsat
    except ImportError:
        return None
    return airsat


def _parse_source_name(stem: str) -> ParsedFilename:
    module = _airsat_module()
    if module is None:
        return ParsedFilename(source_name=stem)
    return module.parse_source_name(stem)


# A vendor scene can carry several product lines (ICEYE ships CSI/GRD/SLC/VID
# next to quick-looks). Pick the primary raster and metadata json by this
# priority instead of directory order.
DATA_PRODUCT_PRIORITY = ("CSI", "GRD", "GEC", "SLC", "VID")
METADATA_PRODUCT_PRIORITY = ("CSI", "GEC", "GRD", "METADATA", "SLC", "VID", "EXTENDED")


def _product_rank(name_lower: str, priority: tuple[str, ...]) -> int:
    for index, token in enumerate(priority):
        if f"_{token.lower()}" in name_lower:
            return index
    return len(priority)


def scan_product_groups(root: str | Path) -> list[ProductGroup]:
    root_path = Path(root)
    files = [root_path] if root_path.is_file() else [path for path in root_path.rglob("*") if path.is_file()]
    groups: dict[str, ProductGroup] = {}

    def assign(group: ProductGroup, path: Path, name_lower: str, suffix: str) -> None:
        """Bucket one file by product-role suffix first, extension second.

        Data-class and metadata buckets keep the highest-priority product file
        instead of whichever sibling happens to sort first.
        """
        if name_lower.endswith(("_preview.tif", "_preview.tiff", "_qlk.tif", "_qlk.tiff")):
            bucket = "preview.jpg" if not group.files.get("preview.jpg") else "preview.png"
        elif name_lower.endswith(("_thumb.png", "_thm.png", "_qlk.png")):
            bucket = "thumbnail.png"
        elif name_lower.endswith("_extended.json"):
            bucket = "metadata.json"
        else:
            bucket = suffix
        existing = group.files.get(bucket)
        if existing is not None:
            if bucket == "metadata.json":
                if _product_rank(name_lower, METADATA_PRODUCT_PRIORITY) >= _product_rank(existing.name.lower(), METADATA_PRODUCT_PRIORITY):
                    return
            elif bucket not in {"stac.json", "preview.png"}:
                return
        group.files[bucket] = path

    for path in files:
        lowered = path.name.lower()
        suffix = path.suffix.lower()
        stem = _source_stem(path)
        group = groups.setdefault(stem, ProductGroup(stem=stem))
        if suffix in IMAGE_EXTENSIONS or suffix in UMBRA_AUXILIARY_EXTENSIONS:
            assign(group, path, lowered, suffix)
        elif lowered.endswith("_extended.json.json"):
            group.files["metadata.json"] = path
        elif suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("type") == "Feature" and payload.get("stac_version"):
                existing = group.files.get("stac.json")
                if existing is None or _product_rank(lowered, METADATA_PRODUCT_PRIORITY) < _product_rank(existing.name.lower(), METADATA_PRODUCT_PRIORITY):
                    group.files["stac.json"] = path
            else:
                # Vendor metadata json (ICEYE *_GRD.json, Umbra *_METADATA.json).
                assign(group, path, lowered, "metadata.json")
        elif lowered.endswith(".meta.incidence.xml"):
            group.files["incidence.xml"] = path
        elif lowered.endswith(".meta.xml"):
            group.files["meta.xml"] = path
        elif lowered.endswith(".result.xml"):
            group.files["result.xml"] = path
        elif lowered.endswith(".thumb.jpg") or lowered.endswith(".thumb.jpeg"):
            group.files["thumbnail.jpg"] = path
        elif lowered.endswith(".thumb.png"):
            group.files["thumbnail.png"] = path
        elif lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
            assign(group, path, lowered, "preview.jpg")
        elif lowered.endswith(".png"):
            assign(group, path, lowered, "preview.png")
        elif lowered.endswith(".log"):
            group.files["log"] = path
    # Umbra packages use one STAC item for several locally named products,
    # e.g. ``scene.stac.v2.json`` beside ``scene_GEC.tif``. Merge those
    # product files into the STAC scene before ingestion. Primary data and
    # metadata buckets keep the highest-priority product file, never let a
    # later sibling overwrite them blindly.
    for group in list(groups.values()):
        if not group.files.get("stac.json"):
            continue
        for candidate_key, candidate in list(groups.items()):
            if candidate is group or not candidate.stem.startswith(f"{group.stem}_"):
                continue
            for bucket, candidate_path in list(candidate.files.items()):
                existing = group.files.get(bucket)
                if bucket in {".tif", ".tiff", ".jp2", "metadata.json", "stac.json"}:
                    priority = DATA_PRODUCT_PRIORITY if bucket not in {"metadata.json", "stac.json"} else METADATA_PRODUCT_PRIORITY
                    if existing is not None and _product_rank(candidate_path.name.lower(), priority) >= _product_rank(existing.name.lower(), priority):
                        continue
                elif existing is not None:
                    continue
                group.files[bucket] = candidate_path
            groups.pop(candidate_key, None)
    # ICEYE ships several product lines for one scene (``_CSI.tif``,
    # ``_GRD.tif``, ``_SLC.tif``, ``_VID.tif`` ...). Group them by their
    # shared stem prefix, then keep the primary data/metadata by product
    # priority (CSI > GRD > SLC > VID) inside the merged group.
    product_tokens = ("CSI", "GRD", "GEC", "SLC", "VID", "QLK", "THM")
    product_line_pattern = re.compile(r"_(" + "|".join(product_tokens) + r")$", re.IGNORECASE)
    merged: dict[str, ProductGroup] = {}
    for group in list(groups.values()):
        match = product_line_pattern.search(group.stem)
        stem = group.stem[: match.start()] if match else group.stem
        target = merged.get(stem)
        if target is None:
            group.stem = stem
            merged[stem] = group
            continue
        for bucket, candidate_path in list(group.files.items()):
            existing = target.files.get(bucket)
            if existing is None:
                target.files[bucket] = candidate_path
                continue
            if bucket in {".tif", ".tiff", ".jp2", "metadata.json"}:
                priority = DATA_PRODUCT_PRIORITY if bucket != "metadata.json" else METADATA_PRODUCT_PRIORITY
                if _product_rank(candidate_path.name.lower(), priority) < _product_rank(existing.name.lower(), priority):
                    target.files[bucket] = candidate_path
        groups.pop(group.stem, None)
    groups = merged
    # Capella quick-look assets come from the sibling GEO product line while
    # the primary data is GEC; normalize GEO -> GEC so they join one scene.
    normalized: dict[str, ProductGroup] = {}
    for group in list(groups.values()):
        stem = re.sub(r"_GEO_", "_GEC_", group.stem, count=1, flags=re.IGNORECASE)
        if stem in normalized:
            normalized[stem].files.update(group.files)
        else:
            group.stem = stem
            normalized[stem] = group
    return [group for group in normalized.values() if group.data_path or group.metadata_path]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip().replace("Z", "+00:00")
    parsed = None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(UTC)


def _polarizations(raw: str | None) -> list[str]:
    if not raw:
        return []
    return list(dict.fromkeys(re.findall(r"[HV]{2}", raw.upper())))


def read_raster_metadata(path: str | Path) -> dict:
    raster_path = Path(path)
    try:
        import rasterio
    except (ImportError, OSError):
        return {"spatial_status": "spatial_pending", "metadata_source": "filename"}
    try:
        with rasterio.open(path) as dataset:
            from rasterio.warp import transform_bounds

            bounds = dataset.bounds
            source_crs = dataset.crs
            if source_crs and str(source_crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                west, south, east, north = transform_bounds(source_crs, "EPSG:4326", *bounds, densify_pts=21)
            else:
                west, south, east, north = bounds.left, bounds.bottom, bounds.right, bounds.top
            bbox = [west, south, east, north]
            return {
                "bbox": bbox,
                "geometry": {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
                "epsg": dataset.crs.to_epsg() if dataset.crs else None,
                "width": dataset.width,
                "height": dataset.height,
                "pixel_spacing_range_m": abs(dataset.res[0]),
                "pixel_spacing_azimuth_m": abs(dataset.res[1]),
                "spatial_status": "ready",
                "metadata_source": "raster",
            }
    except Exception as exc:
        return {"spatial_status": "spatial_pending", "metadata_source": "filename", "spatial_error": str(exc)}


def _json_number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _json_datetime(value):
    return _parse_datetime(str(value)) if value else None


def _json_geometry(payload):
    geometry = payload.get("geometry") if isinstance(payload, dict) else None
    bbox = payload.get("bbox") if isinstance(payload, dict) else None
    if geometry and geometry.get("type") and geometry.get("coordinates"):
        if not bbox:
            coordinates = []
            def walk(value):
                if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                    coordinates.append(value)
                elif isinstance(value, list):
                    for item in value:
                        walk(item)
            walk(geometry.get("coordinates"))
            if coordinates:
                bbox = [min(p[0] for p in coordinates), min(p[1] for p in coordinates), max(p[0] for p in coordinates), max(p[1] for p in coordinates)]
        return geometry, bbox
    return None, bbox


def _apply_stac_metadata(values, payload, vendor):
    properties = payload.get("properties") or {}
    platform = properties.get("platform") or payload.get("platform")
    polarizations = properties.get("sar:polarizations") or []
    if isinstance(polarizations, str):
        polarizations = _polarizations(polarizations)
    polarizations = list(dict.fromkeys(str(item).upper() for item in polarizations))
    range_resolution = _json_number(properties.get("sar:resolution_range"))
    azimuth_resolution = _json_number(properties.get("sar:resolution_azimuth"))
    start = _json_datetime(properties.get("start_datetime"))
    end = _json_datetime(properties.get("end_datetime"))
    center = _json_datetime(properties.get("datetime"))
    if center is None and start and end:
        center = start + (end - start) / 2
    geometry, bbox = _json_geometry(payload)
    values.update({
        "platform_code": str(platform).upper() if platform else values.get("platform_code"),
        "satellite_name": str(platform) if platform else values.get("satellite_name"),
        "sensor": "SAR",
        "imaging_mode": properties.get("sar:instrument_mode") or properties.get("umbra:imaging_mode"),
        "imaging_mode_raw": properties.get("sar:instrument_mode"),
        "imaging_mode_detail": properties.get("umbra:imaging_mode") or properties.get("iceye:processing_mode"),
        "polarization": polarizations[0] if polarizations else values.get("polarization"),
        "polarizations": polarizations or values.get("polarizations", []),
        "polarization_raw": ",".join(polarizations) if polarizations else None,
        "product_level": properties.get("sar:product_type") or properties.get("product_type"),
        "acquisition_time": center,
        "acquisition_start": start,
        "acquisition_end": end,
        "time_assumption": "UTC" if any(str(properties.get(key, "")).endswith("Z") for key in ("datetime", "start_datetime", "end_datetime")) else values.get("time_assumption"),
        "orbit_direction": properties.get("sat:orbit_state") or properties.get("umbra:satellite_track"),
        "look_side": properties.get("sar:observation_direction"),
        "resolution_m": max(item for item in (range_resolution, azimuth_resolution) if item is not None) if range_resolution is not None or azimuth_resolution is not None else None,
        "pixel_spacing_range_m": _json_number(properties.get("sar:pixel_spacing_range")),
        "pixel_spacing_azimuth_m": _json_number(properties.get("sar:pixel_spacing_azimuth")),
        "incidence_angle_near_deg": _json_number(properties.get("iceye:incidence_angle_near")),
        "incidence_angle_far_deg": _json_number(properties.get("iceye:incidence_angle_far")),
        "geometry": geometry or values.get("geometry"),
        "bbox": bbox or values.get("bbox"),
        "metadata_status": "ready",
        "spatial_status": "ready" if geometry else values.get("spatial_status", "partial"),
        "metadata_sources": ["filename", f"{vendor}_stac"],
        "raw_metadata": {"stac_id": payload.get("id"), "properties": properties, "upstream_assets": payload.get("assets", {})},
    })
    shape = properties.get("proj:shape")
    if isinstance(shape, list) and len(shape) >= 2:
        values["height"], values["width"] = int(shape[0]), int(shape[1])
    return values


def parse_stac_json_metadata(path: str | Path, values: dict) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    properties = payload.get("properties") or {}
    constellation = str(properties.get("constellation", "")).lower()
    platform = str(properties.get("platform", "")).lower()
    vendor = "umbra" if constellation == "umbra" or platform.startswith("umbra") else "iceye" if constellation == "iceye" or platform.startswith("iceye") else "stac"
    return _apply_stac_metadata(values, payload, vendor)


def parse_umbra_json_metadata(path: str | Path, values: dict) -> dict:
    """Parse the Umbra task METADATA.json (vendor == "Umbra Space")."""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    collect = (payload.get("collects") or [{}])[0] or {}
    start = _json_datetime(collect.get("startAtUTC"))
    end = _json_datetime(collect.get("endAtUTC"))
    center = start + (end - start) / 2 if start and end else start
    geometry = collect.get("footprintPolygonLla")
    bbox = None
    if isinstance(geometry, dict) and geometry.get("coordinates"):
        points = []

        def collect_points(node):
            if isinstance(node, (list, tuple)):
                if len(node) >= 2 and all(isinstance(item, (int, float)) for item in node[:2]):
                    points.append(node)
                else:
                    for item in node:
                        collect_points(item)

        collect_points(geometry.get("coordinates"))
        if points:
            bbox = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]
    polarizations = [str(p).upper() for p in (collect.get("polarizations") or []) if p]
    resolution = collect.get("maxGroundResolution") or {}
    values.update({
        "platform_code": str(payload.get("umbraSatelliteName") or "UMBRA").upper(),
        "satellite_name": payload.get("umbraSatelliteName"),
        "sensor": "SAR",
        "imaging_mode": payload.get("imagingMode"),
        "imaging_mode_raw": payload.get("imagingMode"),
        "imaging_mode_detail": payload.get("imagingMode"),
        "polarization": polarizations[0] if polarizations else None,
        "polarizations": polarizations,
        "polarization_raw": polarizations[0] if polarizations else None,
        "product_level": "GEC",
        "acquisition_start": start,
        "acquisition_end": end,
        "acquisition_time": center,
        "orbit_direction": collect.get("satelliteTrack"),
        "look_side": collect.get("observationDirection"),
        "incidence_angle_near_deg": _json_number(collect.get("angleIncidenceDegrees")),
        "resolution_m": _json_number(resolution.get("rangeMeters")),
        "pixel_spacing_range_m": _json_number(resolution.get("rangeMeters")),
        "pixel_spacing_azimuth_m": _json_number(resolution.get("azimuthMeters")),
        "geometry": geometry if isinstance(geometry, dict) else None,
        "bbox": bbox,
        "metadata_status": "ready",
        "spatial_status": "ready" if bbox else "partial",
        "metadata_sources": ["filename", "umbra_json"],
        "raw_metadata": {"vendor": payload.get("vendor"), "task_id": collect.get("taskId"), "collect_id": collect.get("id")},
    })
    return values


def parse_capella_json_metadata(path: str | Path, values: dict) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if str(payload.get("vendor", "")).lower() == "umbra space" or payload.get("umbraSatelliteName"):
        return parse_umbra_json_metadata(path, values)
    collect = payload.get("collect") or {}
    image = collect.get("image") or {}
    radar = collect.get("radar") or {}
    state = collect.get("state") or {}
    start = _json_datetime(collect.get("start_timestamp"))
    end = _json_datetime(collect.get("stop_timestamp"))
    center = start + (end - start) / 2 if start and end else start
    product = str(payload.get("product_type") or values.get("source_name") or "").upper()
    geometry, bbox = values.get("geometry"), values.get("bbox")
    coordinate_system = ((image.get("image_geometry") or {}).get("coordinate_system") or {})
    geotransform = (image.get("image_geometry") or {}).get("geotransform")
    if geometry is None and isinstance(geotransform, list) and len(geotransform) == 6 and image.get("columns") and image.get("rows"):
        try:
            from pyproj import CRS, Transformer

            wkt = coordinate_system.get("wkt")
            source_crs = CRS.from_wkt(wkt) if wkt else None
            transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True) if source_crs else None
            cols, rows = float(image["columns"]), float(image["rows"])
            x0, a, b, y0, d, e = [float(item) for item in geotransform]
            corners = [(x0, y0), (x0 + a * cols + b * rows, y0 + d * cols + e * rows), (x0 + b * rows, y0 + e * rows), (x0 + a * cols, y0 + d * cols)]
            if transformer:
                corners = [transformer.transform(x, y) for x, y in corners]
            ring = [[x, y] for x, y in corners]
            ring.append(ring[0])
            geometry = {"type": "Polygon", "coordinates": [ring]}
            bbox = [min(point[0] for point in ring), min(point[1] for point in ring), max(point[0] for point in ring), max(point[1] for point in ring)]
            values["epsg"] = source_crs.to_epsg() if source_crs else values.get("epsg")
        except Exception:
            pass
    if geometry is None and values.get("data_path"):
        raster = read_raster_metadata(values["data_path"])
        geometry, bbox = raster.get("geometry"), raster.get("bbox")
        if raster.get("epsg"):
            values["epsg"] = raster["epsg"]
        values["spatial_status"] = raster.get("spatial_status", values["spatial_status"])
    if geometry is None:
        boundary_path = Path(path).parent / "bb.shp"
        if boundary_path.exists():
            try:
                import fiona
                from pyproj import CRS, Transformer

                with fiona.open(boundary_path) as source:
                    feature = next(iter(source), None)
                    shape = feature.get("geometry") if feature else None
                    source_crs = CRS.from_user_input(source.crs_wkt or source.crs) if (source.crs_wkt or source.crs) else None
                if shape and shape.get("type") and shape.get("coordinates"):
                    if source_crs and source_crs.to_epsg() != 4326:
                        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
                        def transform_coords(value):
                            if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                                return list(transformer.transform(value[0], value[1]))
                            return [transform_coords(item) for item in value]
                        shape["coordinates"] = transform_coords(shape["coordinates"])
                    geometry = shape
                    coordinates = []
                    def collect_coords(value):
                        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                            coordinates.append(value)
                        elif isinstance(value, (list, tuple)):
                            for item in value:
                                collect_coords(item)
                    collect_coords(shape["coordinates"])
                    bbox = [min(p[0] for p in coordinates), min(p[1] for p in coordinates), max(p[0] for p in coordinates), max(p[1] for p in coordinates)]
                    values["epsg"] = 4326
            except Exception:
                pass
    pol = f"{radar.get('transmit_polarization', '')}{radar.get('receive_polarization', '')}".upper() or None
    values.update({
        "platform_code": str(collect.get("platform") or "CAPELLA").upper(),
        "satellite_name": collect.get("platform"), "sensor": "SAR",
        "imaging_mode": collect.get("mode"), "imaging_mode_raw": collect.get("mode"),
        "imaging_mode_detail": "SLIDING_SPOTLIGHT" if "sliding" in str(collect.get("mode", "")).lower() else collect.get("mode"),
        "polarization": pol, "polarizations": [pol] if pol else [], "polarization_raw": pol,
        "product_level": product, "acquisition_start": start, "acquisition_end": end, "acquisition_time": center,
        "orbit_direction": state.get("direction"), "look_side": radar.get("pointing"),
        "resolution_m": max(item for item in (_json_number(image.get("ground_range_resolution")), _json_number(image.get("azimuth_resolution"))) if item is not None) if image else None,
        "pixel_spacing_range_m": _json_number(image.get("pixel_spacing_column")), "pixel_spacing_azimuth_m": _json_number(image.get("pixel_spacing_row")),
        "width": image.get("columns"), "height": image.get("rows"),
        "geometry": geometry, "bbox": bbox, "metadata_status": "ready",
        "spatial_status": "ready" if geometry else "partial", "metadata_sources": ["filename", "capella_json"],
        "raw_metadata": {"product_type": payload.get("product_type"), "collect_id": collect.get("collect_id"), "collect": collect},
    })
    center_pixel = image.get("center_pixel") or {}
    if center_pixel.get("incidence_angle") is not None:
        values["incidence_angle_near_deg"] = _json_number(center_pixel.get("incidence_angle"))
    return values


def parse_product_group(group: ProductGroup) -> dict:
    parsed = _parse_source_name(group.stem)
    values = {
        "source_name": parsed.source_name,
        "platform_code": parsed.platform,
        "satellite_name": None,
        "sensor": None,
        "imaging_mode": None,
        "imaging_mode_raw": None,
        "imaging_mode_code": None,
        "imaging_mode_detail": None,
        "polarization": parsed.polarization,
        "polarizations": [parsed.polarization] if parsed.polarization else [],
        "polarization_raw": None,
        "product_level": parsed.product_level,
        "acquisition_time": parsed.acquisition_time,
        "acquisition_start": None,
        "acquisition_end": None,
        "time_assumption": parsed.time_assumption,
        "orbit_id": None,
        "orbit_direction": None,
        "look_side": None,
        "resolution_m": None,
        "pixel_spacing_range_m": None,
        "pixel_spacing_azimuth_m": None,
        "width": None,
        "height": None,
        "incidence_angle_near_deg": None,
        "incidence_angle_far_deg": None,
        "geometry": None,
        "bbox": None,
        "epsg": 4326,
        "metadata_status": "partial",
        "spatial_status": "partial",
        "metadata_sources": ["filename"],
        "raw_metadata": {},
        "preview_status": "ready" if group.preview_path else "missing",
        "preview_source": "preview" if group.files.get("preview.jpg") or group.files.get("preview.png") else ("thumbnail" if group.files.get("thumbnail.jpg") or group.files.get("thumbnail.png") else None),
        "data_path": str(group.data_path) if group.data_path else None,
        "preview_path": str(group.preview_path) if group.preview_path else None,
        "thumbnail_path": str(group.files.get("thumbnail.jpg") or group.files.get("thumbnail.png")) if group.files.get("thumbnail.jpg") or group.files.get("thumbnail.png") else None,
        "metadata_path": str(group.metadata_path) if group.metadata_path else None,
        "incidence_path": str(group.files["incidence.xml"]) if group.files.get("incidence.xml") else None,
        "result_path": str(group.files["result.xml"]) if group.files.get("result.xml") else None,
        "log_path": str(group.files["log"]) if group.files.get("log") else None,
    }
    if group.files.get("stac.json"):
        values = parse_stac_json_metadata(group.files["stac.json"], values)
    elif group.files.get("metadata.json"):
        values = parse_capella_json_metadata(group.files["metadata.json"], values)
    elif group.metadata_path:
        airsat = _airsat_module()
        if airsat is not None:
            values.update(airsat.parse_meta_xml_values(group, parsed))
    if values["acquisition_time"] is None and values["acquisition_start"] and values["acquisition_end"]:
        values["acquisition_time"] = values["acquisition_start"] + (values["acquisition_end"] - values["acquisition_start"]) / 2
    if values["geometry"] is None and group.data_path:
        raster = read_raster_metadata(group.data_path)
        if raster.get("geometry"):
            for key in ("geometry", "bbox", "epsg", "width", "height", "pixel_spacing_range_m", "pixel_spacing_azimuth_m"):
                if raster.get(key) is not None:
                    values[key] = raster[key]
            values["spatial_status"] = "ready"
            values["metadata_sources"].append("raster")
        elif parsed.center_lon is not None and parsed.center_lat is not None:
            values["geometry"] = {"type": "Point", "coordinates": [parsed.center_lon, parsed.center_lat]}
            values["bbox"] = [parsed.center_lon, parsed.center_lat, parsed.center_lon, parsed.center_lat]
    if values["imaging_mode"] == "STRIPMAP":
        values["imaging_mode_detail"] = "STRIPMAP"
    if group.files.get("log"):
        log_text = group.files["log"].read_text(encoding="utf-8", errors="replace")
        match = re.search(r"IMAGE_MODE:\s*(\d+)", log_text)
        if match:
            code = int(match.group(1))
            values["imaging_mode_code"] = code
            values["imaging_mode_detail"] = {0: "STRIP", 1: "SLIDING_SPOT", 2: "STARING_SPOT", 3: "TOPS"}.get(code)
            values["metadata_sources"].append("log")
    return values


def build_scene_key(metadata: dict) -> tuple[str, str]:
    raw_key = metadata.get("raw_metadata", {}).get("product_id") or metadata.get("source_name") or "unknown-scene"
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(raw_key).strip()).strip("._-").upper()
    identity_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return normalized[:255] or identity_hash, identity_hash
