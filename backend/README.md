# SatHub Backend

Django + Django REST Framework backend for satellite imagery ingestion,
cataloging and search.

## Install

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python manage.py migrate
python manage.py createsuperuser        # or: python manage.py seed_sample_data
python manage.py run_ingestion_worker   # separate terminal
python manage.py runserver 127.0.0.1:8000
```

`seed_sample_data` creates a demo account (`demo` / `demo1234`) and ingests the
three sample scenes from `../sample-data` through the real ingestion pipeline.

## Configuration

Settings read from environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev placeholder | Django secret key |
| `DJANGO_DEBUG` | `true` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated host list |
| `SATHUB_DATA_ROOT` | `<repo>/data` | Data directory root |
| `SATHUB_DUCKDB_PATH` | `<repo>/duckdb/imagery.duckdb` | Search index location |

## Maintenance commands

```bash
python manage.py rebuild_imagery_index   # rebuild DuckDB index + STAC items from the database
```

## Tests

```bash
python manage.py test
```
