# Ingestion & Imagery Hub

Internal satellite imagery ingestion, indexing, and lightweight browsing system.

## Stack

- Backend: Django + Django REST Framework + Django Auth/Admin
- Metadata index: DuckDB
- STAC: generated per imagery item and stored with searchable fields
- Frontend: Vite + React + TypeScript + Ant Design + Leaflet

## Current Scope

- Session-based login with Django auth
- Three primary workspaces: Data, Map, and Services
- Optional project tags for imagery classification; ingestion jobs remain user-audited
- URL text ingestion jobs
- ZIP / 7Z archive and browser folder ingestion jobs
- AIRSAT XML, filename, raster, preview, footprint, and resolution metadata parsing
- Cross-user scene deduplication with one physical copy per scene
- STAC Item generation
- DuckDB imagery index
- Basic imagery search and Leaflet footprint/preview map
- Static imagery datasets with ordered, enabled publication members
- Single-scene and MosaicJSON-backed multi-scene TiTiler services
- Ant Design import/task drawers, imagery list/card views, dataset management, and full-screen map selection
- Soft imagery archive, editable display metadata, DuckDB/STAC projection rebuild
- STAC API search, Bearer access tokens, signed COG asset URLs with HTTP Range
- Data basket, async Manifest/STAC/ZIP delivery, saved searches, and dynamic datasets
- ZIP full-asset delivery with `asset_details` and `checksums.sha256`
- Lightweight OGC API Tiles discovery and `WebMercatorQuad` tile routes alongside existing XYZ/TileJSON
- Leaflet rectangle/polygon spatial search with spatial relations and saved queries
- Asynchronous single-scene `ProcessingJob` integration for bbox/Polygon crop, band selection or expression, and GeoTIFF/PNG output

## Layout

```text
backend/              Django API and worker
frontend/             React + Ant Design app
data/                 Local/NAS file storage root
duckdb/               Local DuckDB imagery index
DEVELOPMENT_PLAN.md   Product and technical plan
```

## Notes

The system stores and searches imagery metadata, previews same-name JPG assets, groups selected scenes into static or query datasets, and publishes single-scene or dataset mosaic services through stable Django TileJSON/XYZ endpoints. It also provides a minimal authenticated STAC API with offset-based `next` links, signed Range asset access, full-asset ZIP delivery, lightweight OGC API Tiles compatibility, and a bounded single-scene processing workflow. These are pragmatic single-server capabilities, not full OGC conformance or a Planetary Computer-scale processing platform. See `backend/README.md` for migration, index rebuild, worker, and startup commands.
