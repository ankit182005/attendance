# settings.py (Render-ready version)
from pathlib import Path
from datetime import timedelta
import os
import dj_database_url
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------
# Security / env
# --------------------
SECRET_KEY = os.environ.get('SECRET_KEY', 'replace-this-with-a-secure-secret')
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS: comma separated list in env, default to all while developing
ALLOWED_HOSTS = [h for h in os.environ.get('ALLOWED_HOSTS', '*').split(',') if h]

# --------------------
# Installed apps
# --------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',

    'attendance',
]

# --------------------
# Middleware
# --------------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise will be inserted below if used (kept in middleware order)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'attendance_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'attendance_project.wsgi.application'

# --------------------
# Database
# --------------------
# Use DATABASE_URL env var (Render provides this when you attach Postgres)
DATABASES = {
    'default': dj_database_url.config(default=os.environ.get('DATABASE_URL'))  # falls back to None (DJ will error if not configured)
}

# --------------------
# Auth / Validation
# --------------------
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --------------------
# Static files (WhiteNoise)
# --------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# enable whitenoise storage when in production
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------
# REST FRAMEWORK + JWT
# --------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
}

# --------------------
# CORS
# --------------------
# You can pass a comma-separated list via env var CORS_ALLOWED_ORIGINS
env_cors = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if env_cors:
    CORS_ALLOWED_ORIGINS = [u.strip() for u in env_cors.split(',') if u.strip()]
else:
    # keep your local defaults for development if not set
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]

# --------------------
# CSV export directory (configurable)
# --------------------
# NOTE: Render's filesystem is ephemeral. For persistent storage use S3 or similar.
CSV_EXPORT_DIR = Path(os.environ.get('CSV_EXPORT_DIR', '/tmp/csv_exports'))
try:
    CSV_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # fallback: use BASE_DIR if /tmp not writable
    CSV_EXPORT_DIR = BASE_DIR / 'csv_exports'
    CSV_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------
# Logging
# --------------------
# Keep file logging locally, but route to stdout for cloud platforms like Render
LOG_DIR = BASE_DIR / "logs"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # ignore failures creating logs dir on platforms where it's not writable
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "standard": {
            "format": "[%(asctime)s] %(levelname)s %(name)s:%(lineno)d — %(message)s"
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
        },
        "attendance_file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "attendance.log"),
            "formatter": "standard",
            "level": "DEBUG",
        },
        "django_file": {
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "django.log"),
            "formatter": "standard",
            "level": "INFO",
        },
    },

    "loggers": {
        "attendance": {
            "handlers": ["console", "attendance_file"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console", "django_file"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": True,
        },
    },
}

# --------------------
# Security / proxy / CSRF
# --------------------
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = [u for u in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if u] or []

# --------------------
# Development defaults (if you want to keep them)
# --------------------
# Keep DEBUG True locally only; set env DEBUG=False on Render
if DEBUG:
    # allow all hosts in debug
    ALLOWED_HOSTS = ["*"]

# --------------------
# End of settings
# --------------------
