"""Preview north-up warp worker.

Reads a raster (possibly rotated / non-north-up affine), warps it to an
axis-aligned EPSG:4326 preview of at most 2400 px, and writes a PNG/NPY array
the caller can encode as JPEG. Runs under the TiTiler Python runtime because
the main runtime cannot import rasterio.

Input (stdin, JSON): {"source": <abs path>, "max_size": 2400}
Output (stdout, JSON): {"ok": true, "width", "height", "bounds": [w,s,e,n], "array_b64"} on success
                        {"ok": false, "error": <message>} otherwise
"""

import base64
import json
import sys

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

MAX_SIZE = 2400


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        source = payload["source"]
        max_size = int(payload.get("max_size") or MAX_SIZE)
        with rasterio.open(source) as ds:
            bounds = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds, densify_pts=21)
            span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
            if span <= 0:
                raise ValueError("invalid bounds")
            # Keep enough pixels for the long axis, capped at max_size.
            scale = min(max_size / max(ds.width, ds.height), 1.0)
            width = max(1, int(round(ds.width * scale)))
            height = max(1, int(round(ds.height * scale)))
            dst_transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], width, height)
            data = ds.read(1)
            dst = np.zeros((height, width), dtype="float32")
            reproject(
                source=data,
                destination=dst,
                src_transform=ds.transform,
                src_crs=ds.crs,
                dst_transform=dst_transform,
                dst_crs="EPSG:4326",
                resampling=Resampling.bilinear,
            )
        sys.stdout.write(
            json.dumps(
                {
                    "ok": True,
                    "width": width,
                    "height": height,
                    "bounds": list(bounds),
                    "array_b64": base64.b64encode(np.asarray(dst, dtype="float32").tobytes()).decode("ascii"),
                }
            )
        )
        return 0
    except Exception as exc:  # pragma: no cover - worker boundary
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)[:300]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
