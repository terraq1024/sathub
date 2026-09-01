import sys
from pathlib import Path

import rasterio
from rasterio.shutil import copy as rio_copy


def main(source_name: str, destination_name: str) -> None:
    source = Path(source_name)
    destination = Path(destination_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.tif")
    temporary.unlink(missing_ok=True)
    with rasterio.open(source) as dataset:
        if not dataset.crs or not dataset.bounds:
            raise ValueError("Source imagery has no valid CRS or bounds.")
        rio_copy(dataset, temporary, driver="COG", compress="DEFLATE", blocksize=512, overview_resampling="average")
    temporary.replace(destination)
    with rasterio.open(destination) as cog:
        if cog.driver != "GTiff" or not cog.crs or cog.width <= 0 or cog.height <= 0:
            raise ValueError("Generated COG failed validation.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
