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

## Quickstart (Docker Compose)

```bash
# 1. Edit docker-compose.yml: set DJANGO_SECRET_KEY and
#    SATHUB_ADMIN_PASSWORD (both default to change-me values).
# 2. Build and start:
docker compose up --build -d
# frontend: http://localhost:8080   backend API: http://localhost:8000
# 3. Log in with the admin account (SATHUB_ADMIN_USERNAME/PASSWORD),
#    then optionally load the demo scenes:
docker compose exec backend python manage.py seed_sample_data
```

The stack runs three containers: the Django API (gunicorn), an
ingestion worker (same image), and an nginx-served frontend. Data
persists in the `sathub-data` / `sathub-duckdb` volumes. The first
backend start runs migrations and creates the admin account defined by
`SATHUB_ADMIN_USERNAME` / `SATHUB_ADMIN_PASSWORD` (only when no admin
exists yet; regular users can then self-register at /register).

## Quickstart (manual)

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_sample_data                   # optional: 3 demo scenes + demo account
python manage.py run_ingestion_worker               # separate terminal
python manage.py runserver 127.0.0.1:8000
```

Frontend (Node 18+):

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Log in with the seeded demo account (`demo` / `demo1234`), open the map, and the three sample scenes are already there with previews. Basemaps: Tianditu vector/imagery and Esri World Imagery, switchable from the map corner.

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
