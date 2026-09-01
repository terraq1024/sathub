# Backend

Django + Django REST Framework API for imagery ingestion and metadata search.

## Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

```powershell
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

In a second terminal, run the lightweight ingestion worker:

```powershell
cd backend
python manage.py run_ingestion_worker
```

Imagery service publication uses a dedicated Python 3.11 runtime on the data disk because the main Miniconda runtime has a broken `pyexpat` DLL that prevents Rasterio/TiTiler startup:

```powershell
uv venv ..\.venv-titiler --python 3.11
$env:UV_CACHE_DIR = "D:\code\airmap\.uv-cache"
uv pip install --python ..\.venv-titiler\Scripts\python.exe -r requirements-titiler.txt
..\.venv-titiler\Scripts\python.exe -m uvicorn titiler_app:app --host 127.0.0.1 --port 8081
```

Run the service publication worker in another terminal:

```powershell
python manage.py run_service_worker
```

Run the data delivery worker in another terminal:

```powershell
python manage.py run_delivery_worker
```

The service worker creates reusable per-image COG files in `..\data\cog`. Dataset publication writes MosaicJSON files to `..\data\mosaics` and keeps the last successful member snapshot online while a newer revision is being published. Django exposes stable TileJSON and XYZ URLs under `/api/services/` and proxies both COG and mosaic tiles from the internal TiTiler process.

Published services also expose a lightweight OGC API Tiles-compatible facade:

```text
GET /api/services/{service_key}/ogcapi
GET /api/services/{service_key}/ogcapi/tiles
GET /api/services/{service_key}/ogcapi/tiles/WebMercatorQuad
GET /api/services/{service_key}/ogcapi/tiles/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}.png
```

These routes reuse the same TiTiler proxy, service status, and public/session visibility rules as XYZ. They currently support only `WebMercatorQuad` PNG tiles and do not claim complete OGC API Tiles conformance or provide WMS/WMTS.

After schema changes, run migrations and rebuild the search/STAC projection:

```powershell
python manage.py migrate
python manage.py rebuild_imagery_index
```

The rebuild command treats SQLite as the authority and regenerates DuckDB rows and STAC Item JSON for every imagery record. Normal imagery edits update the same projection incrementally.

### STAC and external access

The authenticated STAC API is available at `/api/stac/` and supports catalog, collection, item, collection-items, and `/search` endpoints with `bbox`, `datetime`, `ids`, `limit`, `offset`, and metadata `query` filters. Search responses include an offset-based `rel=next` link when more records are available. Create a token from the frontend external access panel or `POST /api/access/tokens`; the response contains the raw token only once. Use `Authorization: Bearer <token>` with the `catalog/read` scope for STAC and `assets/read` for signed asset URLs.

For COG-aware clients, request a signed asset URL from `POST /api/access/assets/sign` and use HTTP Range requests against the returned URL. The signed endpoint validates the asset role, expiry, archive state, storage root, and a configurable 64 MiB maximum single-range size without exposing server filesystem paths. STAC responses only include signed asset URLs when the Bearer token has both `catalog/read` and `assets/read` scopes.

### Data delivery

Selected imagery can be added to the data basket and exported asynchronously as `manifest`, `stac`, or `zip`. The delivery worker writes files under `data/exports`, and downloads are owner/admin-only with a one-day expiry. Manifest/STAC assets use one-day signed URLs. ZIP exports contain every available registered asset role (`data`, `preview`, `thumbnail`, `metadata`, `incidence`, and `log`) under a cleaned per-scene path, plus `manifest.json` and `checksums.sha256`. The manifest preserves the original `assets` mapping and adds `asset_details` entries with role, name, media type, byte size, SHA-256, and signed URL. Missing auxiliary assets are skipped; a missing primary data asset fails the export.

### Online processing

The v7 `ProcessingJob` integration provides bounded asynchronous processing for one registered imagery asset at a time:

- WGS84 bbox or GeoJSON Polygon crop.
- One or more 1-based band indexes, or a restricted `b1`, `b2`, ... arithmetic expression.
- GeoTIFF or PNG output under `data/processing`.
- Owner/admin job access, retry, delete, and result download.

Processing endpoints are mounted under `/api/processing/`:

```text
GET    /api/processing/jobs
POST   /api/processing/jobs
GET    /api/processing/jobs/{job_id}
PATCH  /api/processing/jobs/{job_id}
DELETE /api/processing/jobs/{job_id}
POST   /api/processing/jobs/{job_id}/retry
GET    /api/processing/jobs/{job_id}/download
```

Run the dedicated worker in another terminal:

```powershell
python manage.py run_processing_worker
```

The Django worker claims and records jobs, while raster work is delegated to a controlled subprocess using the Python executable configured by `TITILER_PYTHON`. The request never accepts source or output filesystem paths. This is a single-server, single-scene crop/band workflow; it is not a distributed processing engine and does not provide atmospheric correction, cloud processing, SAR algorithms, arbitrary Python execution, or Planetary Computer-scale compute.

### Runtime order

Run the six backend long-lived processes from `D:\code\airmap`; run the frontend as a seventh development process:

```powershell
# Django API
cd backend
python manage.py runserver 127.0.0.1:8000 --noreload

# Ingestion worker
python manage.py run_ingestion_worker

# Publication worker
python manage.py run_service_worker

# Delivery worker
python manage.py run_delivery_worker

# Processing worker
python manage.py run_processing_worker

# Internal TiTiler COG + MosaicJSON renderer
..\.venv-titiler\Scripts\python.exe -m uvicorn titiler_app:app --host 127.0.0.1 --port 8081

# Frontend (from a separate terminal)
cd ..\frontend
npm run dev -- --host 127.0.0.1
```

The frontend is available at `http://127.0.0.1:5173` and proxies `/api` to Django in development.

### QGIS XYZ access

Add the URL shown by the Imagery Services page as a QGIS XYZ connection. XYZ connections do not communicate dataset bounds to QGIS, so navigate to the bounds returned by the corresponding TileJSON document and use zoom level 8 or higher. Tiles outside an imagery footprint return HTTP 204.

Published high-bit-depth imagery receives a default percentile rescale during publication. This prevents uint16 SAR or optical products from rendering as an apparently empty black tile. A user-provided `rescale` value takes precedence.

Dataset services use `pixel_selection=first`; enabled dataset member order therefore determines overlap priority. Editing dataset membership increments its revision and marks existing services as needing an explicit republish.

Use the Preview action on the Imagery Services page to test the exact public XYZ endpoint in Leaflet. If this preview works but QGIS does not, verify that QGIS can reach the server address (do not use `127.0.0.1` from a different computer), clear the QGIS network tile cache, and navigate to the TileJSON bounds.

Clients that understand OGC API Tiles-style discovery can start from `/api/services/{service_key}/ogcapi`. The current facade is intentionally small and should not be advertised as a fully conformant OGC deployment until it has passed the relevant official conformance suite.

## Notes

The service uses Django's built-in auth/session permissions. ZIP and 7Z archives are handled by `zipfile` and `py7zr`; the worker parses extracted product groups and stores the DuckDB search projection at `../duckdb/imagery.duckdb`.
