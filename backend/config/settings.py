from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

SECRET_KEY = "dev-only-change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]
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
    "apps.publishing",
    "apps.stac_api",
    "apps.access_control",
    "apps.delivery",
    "apps.processing",
    "apps.storage_manager",
    "apps.metadata_registry",
    "apps.catalog_governance",
    "apps.audit_log",
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

DATA_DIR = ROOT_DIR / "data"
UPLOAD_TEMP_DIR = DATA_DIR / "upload-tmp"
STAGING_DIR = DATA_DIR / "staging"
RAW_DIR = DATA_DIR / "raw"
COG_DIR = DATA_DIR / "cog"
MOSAIC_DIR = DATA_DIR / "mosaics"
THUMB_DIR = DATA_DIR / "thumb"
EXPORTS_DIR = DATA_DIR / "exports"
PROCESSING_DIR = DATA_DIR / "processing"
IMAGERY_DIR = DATA_DIR / "imagery"
STAC_DIR = DATA_DIR / "stac"
DUCKDB_PATH = ROOT_DIR / "duckdb" / "imagery.duckdb"

for path in [STAGING_DIR, UPLOAD_TEMP_DIR, RAW_DIR, COG_DIR, MOSAIC_DIR, THUMB_DIR, EXPORTS_DIR, PROCESSING_DIR, IMAGERY_DIR, STAC_DIR, DUCKDB_PATH.parent]:
    path.mkdir(parents=True, exist_ok=True)

# Keep Django's multipart upload spool on the data disk. The system drive may
# be full even when the configured imagery disk still has capacity.
FILE_UPLOAD_TEMP_DIR = str(UPLOAD_TEMP_DIR)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 16 * 1024 * 1024 * 1024
MAX_EXTRACTED_FILES = 100000
URL_DOWNLOAD_TIMEOUT = 120
IMAGERY_DATASET_MAX_MEMBERS = 200
DELIVERY_MAX_ITEMS = 200
ACCESS_MAX_RANGE_BYTES = 64 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 60 * 60
STORAGE_ALLOWED_ROOTS = []
DERIVED_PREVIEW_DIR = DATA_DIR / "derived-previews"

TITILER_BASE_URL = "http://127.0.0.1:8081"
PUBLIC_SERVICE_BASE_URL = "http://127.0.0.1:8000"
TITILER_PYTHON = ROOT_DIR / ".venv-titiler" / "Scripts" / "python.exe"

