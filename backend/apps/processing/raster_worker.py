"""Pure-Python raster worker executed by the isolated TiTiler runtime."""

from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path


MAX_BANDS = 16
MAX_DIMENSION = 8192
MAX_PIXELS = 100_000_000
_BAND_RE = re.compile(r"^b([1-9][0-9]*)$")
_ALLOWED_EXPRESSION_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    ast.Name,
    ast.Load,
    ast.Constant,
)


def normalize_bbox(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox 必须包含四个数字")
    try:
        min_x, min_y, max_x, max_y = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox 必须包含四个数字") from exc
    if not all(math.isfinite(item) for item in (min_x, min_y, max_x, max_y)):
        raise ValueError("bbox 坐标必须为有限数字")
    if not (-180 <= min_x < max_x <= 180 and -90 <= min_y < max_y <= 90):
        raise ValueError("bbox 超出 WGS84 合法范围")
    return [min_x, min_y, max_x, max_y]


def bbox_to_polygon(value):
    min_x, min_y, max_x, max_y = normalize_bbox(value)
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y],
            [min_x, min_y],
        ]],
    }


def validate_polygon(value):
    if not isinstance(value, dict) or value.get("type") != "Polygon":
        raise ValueError("geometry 必须是 GeoJSON Polygon")
    rings = value.get("coordinates")
    if not isinstance(rings, list) or not rings:
        raise ValueError("Polygon 坐标不能为空")
    normalized = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("Polygon 每个环至少需要四个坐标点")
        normalized_ring = []
        unique_points = set()
        for point in ring:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                raise ValueError("Polygon 坐标点格式错误")
            try:
                lon, lat = float(point[0]), float(point[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("Polygon 坐标必须为数字") from exc
            if not math.isfinite(lon) or not math.isfinite(lat):
                raise ValueError("Polygon 坐标必须为有限数字")
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError("Polygon 坐标超出 WGS84 合法范围")
            normalized_ring.append([lon, lat])
            unique_points.add((lon, lat))
        if normalized_ring[0] != normalized_ring[-1]:
            raise ValueError("Polygon 环必须闭合")
        if len(unique_points) < 3:
            raise ValueError("Polygon 环至少需要三个不同坐标点")
        normalized.append(normalized_ring)
    return {"type": "Polygon", "coordinates": normalized}


def validate_expression(expression, band_count=None):
    expression = (expression or "").strip()
    if not expression:
        return None, []
    if len(expression) > 500:
        raise ValueError("表达式长度不能超过 500 个字符")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("表达式语法错误") from exc
    referenced_bands = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_EXPRESSION_NODES):
            raise ValueError("表达式仅支持波段变量和加减乘除运算")
        if isinstance(node, ast.Constant):
            if (
                isinstance(node.value, bool)
                or not isinstance(node.value, (int, float))
                or not math.isfinite(float(node.value))
                or abs(float(node.value)) > 1_000_000_000
            ):
                raise ValueError("表达式包含不支持的常量")
        if isinstance(node, ast.Name):
            match = _BAND_RE.fullmatch(node.id)
            if not match:
                raise ValueError("波段变量必须使用 b1、b2 等格式")
            index = int(match.group(1))
            if band_count is not None and index > band_count:
                raise ValueError(f"表达式引用了不存在的波段 b{index}")
            referenced_bands.add(index)
    return tree, sorted(referenced_bands)


def normalize_bands(value, band_count=None):
    if value in (None, []):
        return []
    if not isinstance(value, list) or len(value) > MAX_BANDS:
        raise ValueError(f"bands 最多包含 {MAX_BANDS} 个波段")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError("bands 必须是从 1 开始的整数列表")
    if len(set(value)) != len(value) or any(item < 1 for item in value):
        raise ValueError("bands 不能重复且必须从 1 开始")
    if band_count is not None and any(item > band_count for item in value):
        raise ValueError(f"bands 超出源影像波段数 {band_count}")
    return list(value)


def _evaluate_expression(tree, arrays, numpy):
    class Evaluator(ast.NodeVisitor):
        def visit_Expression(self, node):
            return self.visit(node.body)

        def visit_Name(self, node):
            return arrays[int(node.id[1:])].astype("float32")

        def visit_Constant(self, node):
            return numpy.asarray(node.value, dtype="float32")

        def visit_BinOp(self, node):
            left = self.visit(node.left)
            right = self.visit(node.right)
            with numpy.errstate(divide="ignore", invalid="ignore", over="ignore"):
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if isinstance(node.op, ast.Div):
                    return numpy.where(right == 0, 0, left / right)
            raise ValueError("表达式包含不支持的运算")

        def visit_UnaryOp(self, node):
            value = self.visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value

    result = numpy.asarray(Evaluator().visit(tree), dtype="float32")
    if result.ndim == 2:
        result = result[numpy.newaxis, ...]
    if result.ndim != 3:
        raise ValueError("表达式结果不是有效栅格")
    return numpy.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def _to_uint8(data, numpy):
    if data.dtype == numpy.uint8:
        return data
    output = numpy.zeros(data.shape, dtype="uint8")
    for index, band in enumerate(data.astype("float32", copy=False)):
        finite = numpy.isfinite(band)
        if not finite.any():
            continue
        low, high = numpy.nanpercentile(band[finite], [2, 98])
        if not math.isfinite(float(low)) or not math.isfinite(float(high)):
            continue
        if low == high:
            output[index] = numpy.clip(band, 0, 255).astype("uint8")
            continue
        output[index] = numpy.clip((band - low) * 255.0 / (high - low), 0, 255).astype("uint8")
    return output


def process(payload):
    import numpy
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    source = Path(payload["source_path"])
    output = Path(payload["output_path"])
    if not source.is_file():
        raise ValueError("源影像文件不存在")
    if not output.parent.is_dir():
        raise ValueError("输出目录不存在")

    crop_type = payload.get("crop_geometry_type")
    geometry = (
        bbox_to_polygon(payload.get("bbox"))
        if crop_type == "bbox"
        else validate_polygon(payload.get("geometry"))
    )
    output_format = payload.get("output_format")
    if output_format not in {"geotiff", "png"}:
        raise ValueError("不支持的输出格式")

    with rasterio.open(source) as dataset:
        if dataset.crs is None:
            raise ValueError("源影像缺少坐标参考系")
        bands = normalize_bands(payload.get("bands"), dataset.count)
        expression_tree, expression_bands = validate_expression(
            payload.get("expression"),
            dataset.count,
        )
        if bands and expression_tree is not None:
            raise ValueError("bands 和 expression 不能同时使用")
        indexes = expression_bands or bands or list(range(1, dataset.count + 1))
        source_geometry = transform_geom(
            "EPSG:4326",
            dataset.crs,
            geometry,
            precision=8,
        )
        data, transform = mask(
            dataset,
            [source_geometry],
            crop=True,
            filled=True,
            indexes=indexes,
        )
        if data.size == 0:
            raise ValueError("裁剪结果为空")
        height, width = int(data.shape[1]), int(data.shape[2])
        if height > MAX_DIMENSION or width > MAX_DIMENSION or height * width > MAX_PIXELS:
            raise ValueError("裁剪结果尺寸过大")
        if expression_tree is not None:
            arrays = {source_index: data[position] for position, source_index in enumerate(indexes)}
            data = _evaluate_expression(expression_tree, arrays, numpy)

        if output_format == "png":
            if data.shape[0] not in {1, 2, 3, 4}:
                raise ValueError("PNG 输出仅支持 1 至 4 个波段")
            data = _to_uint8(data, numpy)
            profile = {
                "driver": "PNG",
                "height": height,
                "width": width,
                "count": int(data.shape[0]),
                "dtype": "uint8",
            }
        else:
            profile = dataset.profile.copy()
            profile.update(
                driver="GTiff",
                height=height,
                width=width,
                count=int(data.shape[0]),
                dtype=str(data.dtype),
                transform=transform,
                compress="deflate",
            )
            if expression_tree is not None:
                profile["nodata"] = None
            if profile.get("photometric") == "ycbcr" and data.shape[0] != 3:
                profile.pop("photometric", None)

        with rasterio.open(output, "w", **profile) as destination:
            destination.write(data)

    return {
        "width": width,
        "height": height,
        "count": int(data.shape[0]),
        "dtype": str(data.dtype),
    }


def main():
    output_path = None
    try:
        payload = json.load(sys.stdin)
        output_path = Path(payload["output_path"])
        result = process(payload)
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        sys.stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
