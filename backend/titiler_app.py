from fastapi import FastAPI
from cogeo_mosaic.backends import MosaicBackend
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import TilerFactory
from titiler.mosaic.factory import MosaicTilerFactory


app = FastAPI(title="AirMap TiTiler", version="1.0.0")
add_exception_handlers(app, DEFAULT_STATUS_CODES)
cog = TilerFactory()
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
mosaic = MosaicTilerFactory(backend=MosaicBackend, name="mosaic")
app.include_router(mosaic.router, prefix="/mosaicjson", tags=["MosaicJSON"])
