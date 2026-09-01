import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import MetadataOverride, MetadataQualityIssue, ParserRun, ParserTemplateVersion


MAX_RULES = 500
MAX_FIELDS = 200
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PATH_PARTS = 20
MAX_REGEX_LENGTH = 256
ALLOWED_SOURCE_TYPES = {"filename_regex", "xml_path", "json_path", "constant", "raster"}
ALLOWED_TRANSFORMS = {"trim", "upper", "lower", "to_number", "parse_datetime", "enum_map", "unit_convert", "coalesce"}
ALLOWED_RASTER_KEYS = {"width", "height", "count", "dtype", "crs", "res_x", "res_y", "bounds", "epsg"}
UNIT_FACTORS = {("m", "km"): 0.001, ("km", "m"): 1000.0, ("m", "cm"): 100.0, ("cm", "m"): 0.01, ("degree", "radian"): 0.017453292519943295, ("radian", "degree"): 57.29577951308232}
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")


class RuleValidationError(ValueError):
    pass


class RuleExecutionError(ValueError):
    pass


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _safe_regex(pattern: str) -> re.Pattern:
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_REGEX_LENGTH:
        raise RuleValidationError("regex must be a non-empty string of at most 256 characters")
    if re.search(r"\([^)]*[+*][^)]*\)[+*]", pattern):
        raise RuleValidationError("nested quantifiers are not allowed")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise RuleValidationError(f"invalid regex: {exc}") from exc


def _safe_path(path: str) -> list[str]:
    parts = path.split("/") if isinstance(path, str) else []
    if not isinstance(path, str) or not path or len(parts) > MAX_PATH_PARTS or any(part in {".", ".."} for part in parts) or not SAFE_PATH_RE.fullmatch(path):
        raise RuleValidationError("path must contain simple slash-separated names only")
    return parts


def _validate_transform(transform: Any) -> None:
    if isinstance(transform, str):
        op, args = transform, {}
    elif isinstance(transform, dict):
        op, args = transform.get("op"), transform
    else:
        raise RuleValidationError("transform must be a string or object")
    if op not in ALLOWED_TRANSFORMS:
        raise RuleValidationError(f"unsupported transform: {op}")
    if op == "enum_map" and not isinstance(args.get("mapping"), dict):
        raise RuleValidationError("enum_map requires a mapping object")
    if op == "unit_convert" and (args.get("from") or args.get("to")) and (args.get("from"), args.get("to")) not in UNIT_FACTORS:
        raise RuleValidationError("unit conversion is not in the allowlist")


def validate_rules(rules: Any) -> dict:
    if not isinstance(rules, dict) or _json_size(rules) > MAX_JSON_BYTES:
        raise RuleValidationError("rules must be a JSON object within the size limit")
    fields = rules.get("fields")
    if not isinstance(fields, list) or not fields or len(fields) > MAX_FIELDS:
        raise RuleValidationError("rules.fields must contain 1 to 200 field rules")
    rule_count = 0
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get("key"), str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,119}", field["key"]):
            raise RuleValidationError("each field needs a safe key")
        sources = field.get("sources", [])
        if not isinstance(sources, list) or not sources or len(sources) > 20:
            raise RuleValidationError(f"field {field['key']} needs 1 to 20 sources")
        for source in sources:
            rule_count += 1
            if rule_count > MAX_RULES or not isinstance(source, dict):
                raise RuleValidationError("too many or invalid rules")
            source_type = source.get("type", next((key for key in ALLOWED_SOURCE_TYPES if key in source), None))
            if source_type not in ALLOWED_SOURCE_TYPES:
                raise RuleValidationError(f"unsupported source type for {field['key']}")
            if source_type == "filename_regex":
                _safe_regex(source.get("pattern", source.get("regex")))
                if source.get("group") is not None and not isinstance(source["group"], (str, int)):
                    raise RuleValidationError("filename regex group must be a string or integer")
            elif source_type in {"xml_path", "json_path"}:
                _safe_path(source.get("path", ""))
                if source.get("asset") is not None and not isinstance(source["asset"], str):
                    raise RuleValidationError("asset role must be a string")
            elif source_type == "raster" and source.get("key") not in ALLOWED_RASTER_KEYS:
                raise RuleValidationError("raster key is not allowed")
            for transform in field.get("transforms", field.get("transform", [])) or []:
                _validate_transform(transform)
    matcher = rules.get("match")
    if matcher is not None and not isinstance(matcher, dict):
        raise RuleValidationError("match must be an object")
    return rules


def _path_for_asset(group, role: str | None, suffix: str | None = None) -> Path | None:
    if role:
        aliases = {"metadata": "meta.xml", "incidence": "incidence.xml", "log": "log", "data": None, "preview": "preview.jpg", "thumbnail": "thumbnail.jpg"}
        path = group.files.get(aliases.get(role, role))
    else:
        path = None
    if path is None and suffix:
        path = next((value for value in group.files.values() if str(value).lower().endswith(suffix.lower())), None)
    return Path(path) if path else None


def _read_limited(path: Path, limit: int = MAX_TEXT_BYTES) -> bytes:
    if not path.is_file():
        raise RuleExecutionError("input asset is not a regular file")
    if path.stat().st_size > limit:
        raise RuleExecutionError("input asset exceeds the configured size limit")
    return path.read_bytes()


def _xml_value(path: Path, expression: str) -> str | None:
    _safe_path(expression)
    from lxml import etree

    raw = _read_limited(path)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
    try:
        root = etree.fromstring(raw, parser=parser)
    except (etree.XMLSyntaxError, UnicodeDecodeError):
        root = etree.fromstring(raw.decode("gb18030", errors="replace").encode("utf-8"), parser=parser)
    parts = expression.split("/")
    nodes = [root]
    for part in parts:
        nodes = [child for node in nodes for child in node if etree.QName(child).localname == part]
        if not nodes:
            break
    return nodes[0].text.strip() if nodes and nodes[0].text else None


def _json_value(path: Path, expression: str) -> Any:
    _safe_path(expression.replace(".", "/"))
    raw = _read_limited(path, MAX_JSON_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuleExecutionError("invalid JSON metadata asset") from exc
    for part in expression.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _raster_value(path: Path, key: str) -> Any:
    if key not in ALLOWED_RASTER_KEYS:
        raise RuleExecutionError("raster metadata key is not allowed")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise RuleExecutionError("raster input exceeds the configured size limit")
    try:
        import rasterio
        with rasterio.open(path) as dataset:
            values = {"width": dataset.width, "height": dataset.height, "count": dataset.count, "dtype": dataset.dtypes[0], "crs": dataset.crs.to_string() if dataset.crs else None, "res_x": dataset.res[0], "res_y": dataset.res[1], "bounds": list(dataset.bounds), "epsg": dataset.crs.to_epsg() if dataset.crs else None}
            return values[key]
    except Exception as exc:
        raise RuleExecutionError(f"raster metadata read failed: {exc}") from exc


def _source_value(source: dict, group, filename: str, raster_cache: dict) -> tuple[Any, dict]:
    source_type = source.get("type", next((key for key in ALLOWED_SOURCE_TYPES if key in source), None))
    if source_type == "filename_regex":
        pattern = source.get("pattern", source.get("regex"))
        match = _safe_regex(pattern).search(filename)
        if not match:
            return None, {"source": "filename", "pattern": pattern}
        group_name = source.get("group", 0)
        return match.group(group_name), {"source": "filename", "pattern": pattern, "group": group_name}
    if source_type == "constant":
        return source.get("value"), {"source": "constant"}
    if source_type == "xml_path":
        path = _path_for_asset(group, source.get("asset", "metadata"), ".xml")
        return (None, {"source": source.get("asset", "metadata"), "path": source["path"]}) if not path else (_xml_value(path, source["path"]), {"source": str(path.name), "path": source["path"]})
    if source_type == "json_path":
        path = _path_for_asset(group, source.get("asset"), ".json")
        return (None, {"source": source.get("asset", "json"), "path": source["path"]}) if not path else (_json_value(path, source["path"]), {"source": str(path.name), "path": source["path"]})
    if source_type == "raster":
        path = _path_for_asset(group, "data") or group.data_path
        if not path:
            return None, {"source": "raster", "key": source.get("key")}
        cache_key = str(path)
        if cache_key not in raster_cache:
            raster_cache[cache_key] = {}
        if source["key"] not in raster_cache[cache_key]:
            raster_cache[cache_key][source["key"]] = _raster_value(path, source["key"])
        return raster_cache[cache_key][source["key"]], {"source": str(path.name), "key": source["key"]}
    raise RuleExecutionError("unsupported source type")


def _transform(value: Any, transform: Any) -> Any:
    op = transform if isinstance(transform, str) else transform.get("op")
    args = {} if isinstance(transform, str) else transform
    if op == "coalesce":
        if value is not None and value != "":
            return value
        for candidate in args.get("values", []):
            if candidate is not None and candidate != "":
                return candidate
        return None
    if value is None:
        return None
    if op == "trim":
        return value.strip() if isinstance(value, str) else value
    if op == "upper":
        return value.upper() if isinstance(value, str) else value
    if op == "lower":
        return value.lower() if isinstance(value, str) else value
    if op == "to_number":
        return float(value) if "." in str(value) else int(value)
    if op == "parse_datetime":
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.strptime(text, args["format"]) if args.get("format") else datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(args.get("timezone", "Asia/Shanghai")))
        return parsed.astimezone(ZoneInfo("UTC")).isoformat()
    if op == "enum_map":
        return args.get("mapping", {}).get(str(value), value)
    if op == "unit_convert":
        factor = UNIT_FACTORS.get((args.get("from"), args.get("to")))
        return value * factor if factor is not None else value
    if op == "coalesce":
        return value
    raise RuleExecutionError(f"unsupported transform: {op}")


def _matches(matcher: dict, group) -> bool:
    if not matcher:
        return True
    filename = str(group.stem)
    if "filename_regex" in matcher and not _safe_regex(matcher["filename_regex"]).search(filename):
        return False
    if "asset_exists" in matcher:
        roles = matcher["asset_exists"] if isinstance(matcher["asset_exists"], list) else [matcher["asset_exists"]]
        for role in roles:
            if _path_for_asset(group, role) is None and not (role == "data" and group.data_path):
                return False
    if "all" in matcher and not all(_matches(item, group) for item in matcher["all"]):
        return False
    if "any" in matcher and not any(_matches(item, group) for item in matcher["any"]):
        return False
    return True


def _validate_value(field: dict, value: Any) -> str | None:
    if value is None:
        return "required field is missing" if field.get("required") else None
    data_type = field.get("data_type", field.get("type", "string"))
    if data_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        return "expected integer"
    if data_type == "float" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return "expected number"
    if data_type == "enum" and field.get("enum_values") and value not in field["enum_values"]:
        return "value is outside enum_values"
    validation = field.get("validation", {})
    if isinstance(value, (int, float)) and validation.get("min") is not None and value < validation["min"]:
        return "value is below minimum"
    if isinstance(value, (int, float)) and validation.get("max") is not None and value > validation["max"]:
        return "value is above maximum"
    return None


def execute_rules(group, rules: dict) -> dict:
    validate_rules(rules)
    filename = str(group.stem)
    result: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
    issues: list[dict] = []
    raster_cache: dict = {}
    for field in rules["fields"]:
        candidates = []
        for index, source in enumerate(field["sources"]):
            try:
                value, source_info = _source_value(source, group, filename, raster_cache)
                for transform in field.get("transforms", field.get("transform", [])) or []:
                    value = _transform(value, transform)
                if value is not None and value != "":
                    candidates.append((source.get("priority", len(field["sources"]) - index), value, source_info))
            except (RuleExecutionError, RuleValidationError, ValueError, TypeError) as exc:
                issues.append({"code": "source_error", "severity": "warning", "field_key": field["key"], "message": str(exc)})
        candidates.sort(key=lambda item: item[0], reverse=True)
        value = candidates[0][1] if candidates else None
        result[field["key"]] = value
        provenance[field["key"]] = {"value": value, "raw_value": value, "source": candidates[0][2] if candidates else None, "candidates": [item[2] | {"value": item[1], "priority": item[0]} for item in candidates]}
        if len({json.dumps(item[1], sort_keys=True, default=str) for item in candidates}) > 1:
            issues.append({"code": "source_conflict", "severity": "warning", "field_key": field["key"], "message": "multiple metadata sources contain different values", "details": {"candidates": provenance[field["key"]]["candidates"]}})
        error = _validate_value(field, value)
        if error:
            issues.append({"code": "quality_validation", "severity": "error" if field.get("required") else "warning", "field_key": field["key"], "message": error})
    return {"values": result, "provenance": provenance, "issues": issues}


def _template_candidates():
    return ParserTemplateVersion.objects.select_related("template", "template__schema").filter(status=ParserTemplateVersion.STATUS_PUBLISHED, template__status="active", template__schema__status="active").order_by("-template__priority", "-created_at")


def parse_product_group_with_registry(group, fallback_callable: Callable | None = None) -> dict:
    for version in _template_candidates():
        if _matches(version.template.matcher, group) and _matches(version.rules.get("match", {}), group):
            parsed = execute_rules(group, version.rules)
            flat = dict(parsed["values"])
            flat["metadata_provenance"] = parsed["provenance"]
            flat["metadata_quality_issues"] = parsed["issues"]
            flat["metadata_registry"] = {"template": version.template.name, "version": version.version, "schema": version.template.schema.code}
            return flat
    if fallback_callable is None:
        from apps.imagery.metadata import parse_product_group
        fallback_callable = parse_product_group
    return fallback_callable(group)


def _fingerprint(group) -> str:
    digest = hashlib.sha256()
    for key, path in sorted(group.files.items()):
        path = Path(path)
        digest.update(key.encode())
        digest.update(str(path).encode())
        if path.is_file():
            digest.update(str(path.stat().st_size).encode())
            digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


def run_parser(group, *, imagery=None, parser_version=None, user=None, dry_run=False) -> tuple[ParserRun | None, dict]:
    version = parser_version
    if version is None:
        version = next((candidate for candidate in _template_candidates() if _matches(candidate.template.matcher, group) and _matches(candidate.rules.get("match", {}), group)), None)
    if version is None:
        from apps.imagery.metadata import parse_product_group
        parsed = parse_product_group(group)
        return None, {"values": parsed, "provenance": {}, "issues": []}
    parsed = execute_rules(group, version.rules)
    if imagery is not None:
        overrides = MetadataOverride.objects.filter(imagery=imagery, locked=True).order_by("field_key", "-created_at")
        for override in overrides:
            if override.field_key not in parsed["values"]:
                continue
            parsed["values"][override.field_key] = override.value
            parsed["provenance"][override.field_key] = {
                "value": override.value,
                "raw_value": override.raw_value,
                "source": "manual_override",
                "reason": override.reason,
                "override_id": override.pk,
            }
    if dry_run:
        return None, parsed
    with transaction.atomic():
        run = ParserRun.objects.create(imagery=imagery, parser_version=version, status=ParserRun.STATUS_RUNNING, input_fingerprint=_fingerprint(group), dry_run=False)
        run.values = parsed["values"]
        run.provenance = parsed["provenance"]
        run.warnings = [issue for issue in parsed["issues"] if issue["severity"] != "error"]
        run.errors = [issue for issue in parsed["issues"] if issue["severity"] == "error"]
        run.status = ParserRun.STATUS_FAILED if run.errors else ParserRun.STATUS_SUCCEEDED
        run.finished_at = timezone.now()
        run.save(update_fields=["values", "provenance", "warnings", "errors", "status", "finished_at"])
        for issue in parsed["issues"]:
            MetadataQualityIssue.objects.create(imagery=imagery, parser_run=run, field_key=issue.get("field_key", ""), code=issue["code"], severity=issue["severity"], message=issue["message"], details=issue.get("details", {}))
        if imagery is not None:
            _apply_to_imagery(imagery, parsed)
    return run, parsed


def _apply_to_imagery(imagery, parsed: dict) -> None:
    values = parsed["values"]
    known_fields = {field.name for field in imagery._meta.fields}
    update_fields = []
    aliases = {"platform": "platform_code", "satellite": "satellite_name", "datetime": "acquisition_time"}
    for key, value in values.items():
        target = aliases.get(key, key)
        if target not in known_fields:
            continue
        if target.endswith("_time") and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
        setattr(imagery, target, value)
        update_fields.append(target)
    raw = dict(imagery.raw_metadata or {})
    raw["metadata_registry"] = {"values": values, "provenance": parsed["provenance"]}
    imagery.raw_metadata = raw
    update_fields.append("raw_metadata")
    if update_fields:
        imagery.save(update_fields=list(dict.fromkeys(update_fields)))
