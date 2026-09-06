# SatHub — Imagery Hub

A lightweight, self-hosted hub for satellite imagery: bring your scattered scenes together, catalog them automatically, search them in seconds, and preview them on a map — straight from the browser.

SatHub OSS covers the "data home" part of the imagery workflow:

```
ingest -> catalog (STAC) -> search -> preview on map -> organize (datasets)
```

## Features

- **Flexible ingestion** — import from URL lists, ZIP/7Z archives, or whole folders dragged into the browser. Every import runs as an async job with per-item status and retry.
- **Directory ingestion (reference mode)** — register an existing local or NAS/SMB directory as a storage endpoint, scan it, and ingest scenes **in place without copying**: the platform catalogs the files and serves previews, while the originals stay where they are. Missing files are detected on rescan; two consecutive scans confirm deletion.
- **Automatic metadata & cataloging** — reads raster metadata (GDAL/rasterio), STAC items, and vendor JSON sidecars (Capella, Umbra, ICEYE); derives footprints, bounds, resolution and acquisition time; writes one STAC Item per scene and a DuckDB search index.
- **Content deduplication** — SHA-256 identity hashing across users; the same scene uploaded twice is stored once and re-tagged instead.
- **Catalog search** — combine keyword, satellite, sensor, product level, polarization, time range and facets; draw rectangles or polygons on the map (intersects / contains / within); save queries for reuse.
- **One-map view** — all footprints on a Leaflet map; click to overlay the preview image with adjustable opacity; browser-side TIFF quick-look transcoding for vendor previews.
- **Generated previews** — scenes without a sidecar preview get a cached downsampled preview generated at ingest, so every scene is visible on the map.
- **Datasets** — static datasets (curated, ordered) and dynamic datasets (query-defined, auto-refreshed on ingest).
- **STAC API** — read-only STAC API (`/api/stac/`) with bbox / datetime / query search, so third-party tools can consume your catalog.
- **Lightweight governance** — Django accounts, project tags, soft archive, display-name editing, DuckDB/STAC projection rebuild.

## What is not in this edition

This repository is the open edition. The following capabilities are part of the commercial edition and are intentionally not included:

- tile service publishing (XYZ / TileJSON / OGC API Tiles, single-scene and mosaic)
- online processing (crop, band selection, band math)
- export packaging (data basket, ZIP manifests with checksums, snapshot versioning)
- configurable metadata parser templates, catalog governance (classifications, tags, administrative regions), audit log, API token auth

The open edition renders imagery inside its own map; it does not expose tile service endpoints.

## Quickstart (plain — recommended)

Three moving parts only: a Python backend, one background worker, and a
static frontend build. No containers required.

**1. Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_admin                    # creates admin from SATHUB_ADMIN_USERNAME/PASSWORD (see below)
python manage.py seed_sample_data                   # optional: 3 demo scenes + demo account
```

**2. Ingestion worker** (separate terminal):

```bash
source ../backend/.venv/bin/activate                # Windows: ..\backend\.venv\Scripts\activate
python manage.py run_ingestion_worker
```

**3. Frontend** (Node 18+):

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1      # development, proxies /api to :8000
# or for serving real users:
npm run build                        # outputs frontend/dist — serve it with nginx/caddy
```

**Log in**: with the seeded demo account (`demo` / `demo1234`) or the
bootstrap admin, then register more users at `/register`. Basemaps:
Tianditu vector/imagery and Esri World Imagery, switchable from the map
corner.

**Environment variables** (see `.env.example` and the table in
[backend/README.md](backend/README.md)): `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `SATHUB_DATA_ROOT`,
`SATHUB_DUCKDB_PATH`, `SATHUB_ADMIN_USERNAME` / `SATHUB_ADMIN_PASSWORD`
(first-admin bootstrap), and the optional `SATHUB_WARP_PYTHON` (see
below).

**Production notes**:

- Serve the backend with gunicorn
  (`pip install gunicorn && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3`)
  behind nginx/Caddy, which also serves `frontend/dist` as static files
  and proxies `/api` + `/admin` to the backend.
- Run `run_ingestion_worker` under a process manager (systemd unit,
  pm2, NSSM on Windows) — it must stay alive for imports to process.
- `rasterio` ships prebuilt wheels for Linux/macOS/Windows; if your host
  has a broken GDAL/expat stack (seen on some Windows conda setups),
  create a small isolated venv with just rasterio and point
  `SATHUB_WARP_PYTHON` at its interpreter — the app probes it and uses
  it only for warping rotated rasters into north-up previews. Without a
  healthy rasterio anywhere, previews degrade gracefully to unwarped.

## Alternative: Docker Compose

Prefer containers? The repo ships a three-container stack (gunicorn
backend, ingestion worker, nginx frontend):

```bash
cp .env.example .env      # set DJANGO_SECRET_KEY / SATHUB_ADMIN_PASSWORD
docker compose up --build -d
# frontend: http://localhost:8080   backend API: http://localhost:8000
```

Every value in `docker-compose.yml` can be overridden from `.env`
(`SATHUB_ADMIN_USERNAME`, `SATHUB_ADMIN_PASSWORD`, `SATHUB_BACKEND_PORT`,
`SATHUB_FRONTEND_PORT`, `DJANGO_ALLOWED_HOSTS`, ...). The first backend
start runs migrations and creates the admin account; regular users can
then self-register. Data persists in the `sathub-data` /
`sathub-duckdb` volumes. Put your own TLS-terminating reverse proxy in
front for production.


## Sample data

`sample-data/` contains three small synthetic GeoTIFF scenes (Hefei, Qingdao, Chengdu). `seed_sample_data` ingests them through the real ingestion pipeline (archive -> scan -> parse -> index -> preview).

## API overview

| Area | Endpoint |
|---|---|
| Auth / capabilities | `/api/auth/*`, `/api/auth/capabilities` |
| Ingestion | `/api/ingestion/jobs/*` |
| Directory ingestion | `/api/storage/endpoints/*` (register, check, scan, ingest) |
| Catalog & search | `/api/imagery`, `/api/imagery/map`, `/api/imagery/facets` |
| Datasets | `/api/imagery/datasets/*` |
| STAC | `/api/stac/` (core, collections, search) |

## Tech stack

Django + DRF · DuckDB (search index) · rasterio/tifffile (raster metadata & previews) · STAC 1.0 · React + TypeScript + Ant Design + Leaflet.

## Repository layout

```
backend/    Django API, ingestion worker, DuckDB index
frontend/   React + Ant Design workbench (data catalog + map)
sample-data/ small demo scenes for the seed command
```

## License

[Apache-2.0](LICENSE)
