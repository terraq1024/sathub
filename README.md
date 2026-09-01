# Airmap — Imagery Hub

A lightweight, self-hosted hub for satellite imagery: bring your scattered scenes together, catalog them automatically, search them in seconds, and preview them on a map — straight from the browser.

Airmap OSS covers the "data home" part of the imagery workflow:

```
ingest -> catalog (STAC) -> search -> preview on map -> organize (datasets)
```

## Features

- **Flexible ingestion** — import from URL lists, ZIP/7Z archives, or whole folders dragged into the browser. Every import runs as an async job with per-item status and retry.
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
- delivery (data basket, ZIP manifests with checksums, frozen delivery snapshots)
- storage endpoint scanning (NAS/S3 registration, scheduled scans, reconciliation)
- configurable metadata parser templates, catalog governance (classifications, tags, administrative regions), audit log, API token auth

The open edition renders imagery inside its own map; it does not expose tile service endpoints.

## Quickstart (Docker Compose)

```bash
docker compose up --build
# backend:  http://localhost:8000  (Django API + admin)
# frontend: http://localhost:8080
```

Then create a demo catalog inside the backend container:

```bash
docker compose exec backend python manage.py seed_sample_data
```

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

Log in with the seeded demo account (`demo` / `demo1234`), open the map, and the three sample scenes are already there with previews. The optional basemap uses Tianditu; set your own token in `frontend/.env` (`VITE_TIANDITU_TOKEN`).

## Sample data

`sample-data/` contains three small synthetic GeoTIFF scenes (Hefei, Qingdao, Chengdu). `seed_sample_data` ingests them through the real ingestion pipeline (archive -> scan -> parse -> index -> preview).

## API overview

| Area | Endpoint |
|---|---|
| Auth / capabilities | `/api/auth/*`, `/api/auth/capabilities` |
| Ingestion | `/api/ingestion/jobs/*` |
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
