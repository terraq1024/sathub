import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog_governance.models import AdministrativeUnit
from apps.catalog_governance.services import derived_parent_code, geometry_bbox, normalize_gb_code, point_in_geometry


LEVEL_FILES = {
    "province": "中国_省.geojson",
    "city": "中国_市.geojson",
    "county": "中国_县.geojson",
}


def _read_geojson(path):
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            document = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"无法读取 {path}: {exc}") from exc
    if document.get("type") != "FeatureCollection":
        raise CommandError(f"{path} 不是 FeatureCollection")
    crs = document.get("crs") or {}
    crs_text = json.dumps(crs, ensure_ascii=False).lower()
    if crs and "4490" not in crs_text:
        raise CommandError(f"{path} 的 CRS 不是 EPSG:4490")
    return document


class Command(BaseCommand):
    help = "导入天地图省、市、县行政区 GeoJSON，并建立省市县父级关系"

    def add_arguments(self, parser):
        parser.add_argument("directory", nargs="?", default=r"D:\行政区划天地图")
        parser.add_argument("--source-version", default="")
        parser.add_argument("--replace-version", action="store_true")

    def handle(self, *args, **options):
        directory = Path(options["directory"])
        if not directory.is_dir():
            raise CommandError(f"行政区目录不存在: {directory}")
        version = options["source_version"] or self._default_version(directory)
        staged = []
        skipped = 0
        for level, filename in LEVEL_FILES.items():
            path = directory / filename
            if not path.exists():
                raise CommandError(f"缺少行政区文件: {path}")
            for feature in _read_geojson(path).get("features", []):
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                name = str(properties.get("name") or properties.get("NAME") or "").strip()
                if name == "境界线" or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                    skipped += 1
                    continue
                if not name:
                    skipped += 1
                    continue
                try:
                    bbox = geometry_bbox(geometry)
                    code = normalize_gb_code(properties.get("gb") or properties.get("GB"), fallback_name=f"{level}:{name}")
                except (TypeError, ValueError) as exc:
                    self.stderr.write(f"跳过 {path.name}:{name}: {exc}")
                    skipped += 1
                    continue
                staged.append({"level": level, "code": code, "name": name, "geometry": geometry, "bbox": bbox, "source_file": path.name})

        with transaction.atomic():
            if options["replace_version"]:
                AdministrativeUnit.objects.filter(source_version=version).delete()
            units = {}
            for item in staged:
                unit, _ = AdministrativeUnit.objects.update_or_create(
                    level=item["level"], code=item["code"], source_version=version,
                    defaults={**item, "parent": None, "is_valid": True},
                )
                units[(item["level"], item["code"])] = unit
            for item in staged:
                parent = None
                parent_code = derived_parent_code(item["code"], item["level"])
                if parent_code:
                    parent = units.get(("province" if item["level"] == "city" else "city", parent_code))
                if parent is None and item["level"] != "province":
                    parent = self._find_parent_by_geometry(item, units, item["level"])
                unit = units[(item["level"], item["code"])]
                if unit.parent_id != (parent.pk if parent else None):
                    unit.parent = parent
                    unit.save(update_fields=["parent", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"已导入 {len(staged)} 个行政区，跳过 {skipped} 个要素，来源版本 {version}"))

    @staticmethod
    def _find_parent_by_geometry(item, units, level):
        parent_level = "province" if level == "city" else "city"
        center = [(item["bbox"][0] + item["bbox"][2]) / 2, (item["bbox"][1] + item["bbox"][3]) / 2]
        for (candidate_level, _), candidate in units.items():
            if candidate_level == parent_level and point_in_geometry(center, candidate.geometry):
                return candidate
        return None

    @staticmethod
    def _default_version(directory):
        mtimes = [path.stat().st_mtime for path in directory.glob("*.geojson")]
        stamp = datetime.fromtimestamp(max(mtimes) if mtimes else directory.stat().st_mtime).strftime("%Y%m%d")
        return f"天地图-{stamp}"
