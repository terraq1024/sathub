import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://127.0.0.1:5175",
    "http://localhost:5175",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.projects",
    "apps.ingestion",
    "apps.imagery",
    "apps.stac_api",
    "apps.storage_manager",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CSRF_FAILURE_VIEW = "config.csrf.csrf_failure"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ROOT_DIR / "data" / "app.sqlite3",
    }
}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

def _from_env(value: str, default: str) -> Path:
    path = Path(value) if value else Path(default)
    return path.resolve() if path.is_absolute() else (ROOT_DIR / path).resolve()


DATA_DIR = _from_env(os.environ.get("SATHUB_DATA_ROOT"), str(ROOT_DIR / "data"))
DUCKDB_PATH = _from_env(os.environ.get("SATHUB_DUCKDB_PATH"), str(ROOT_DIR / "duckdb" / "imagery.duckdb"))
UPLOAD_TEMP_DIR = DATA_DIR / "upload-tmp"
STAGING_DIR = DATA_DIR / "staging"
RAW_DIR = DATA_DIR / "raw"
THUMB_DIR = DATA_DIR / "thumb"
IMAGERY_DIR = DATA_DIR / "imagery"
STAC_DIR = DATA_DIR / "stac"

for path in [STAGING_DIR, UPLOAD_TEMP_DIR, RAW_DIR, THUMB_DIR, IMAGERY_DIR, STAC_DIR, DUCKDB_PATH.parent]:
    path.mkdir(parents=True, exist_ok=True)

# Keep Django's multipart upload spool on the data disk. The system drive may
# be full even when the configured imagery disk still has capacity.
FILE_UPLOAD_TEMP_DIR = str(UPLOAD_TEMP_DIR)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 16 * 1024 * 1024 * 1024
MAX_EXTRACTED_FILES = 100000
URL_DOWNLOAD_TIMEOUT = 120
IMAGERY_DATASET_MAX_MEMBERS = 200
DERIVED_PREVIEW_DIR = DATA_DIR / "derived-previews"

# Optional: an isolated Python runtime with rasterio, used only to warp
# rotated rasters into north-up previews. When absent, previews fall back to
# the tifffile/PIL path and rotated scenes are previewed unwarped.
TITILER_PYTHON = ROOT_DIR / ".venv-titiler" / "Scripts" / "python.exe"

