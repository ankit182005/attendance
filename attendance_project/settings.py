from pathlib import Path
from datetime import timedelta
import os
import sys

# Base dir
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------
# Security
# --------------------
SECRET_KEY = os.environ.get('SECRET_KEY', 'replace-this-in-production')
#DEBUG = True  # local
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')  # prod

#ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # local
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')  # prod

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
    'whitenoise.middleware.WhiteNoiseMiddleware',  # WhiteNoise
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
        'DIRS': [
            BASE_DIR / 'attendance' / 'templates'
        ],
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
# Database (SQLite only)
# --------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# --------------------
# Password validation
# --------------------
AUTH_PASSWORD_VALIDATORS = []

# --------------------
# Internationalization / Timezone
# --------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'   # set to your local timezone
USE_I18N = True
USE_TZ = True

# --------------------
# Static + WhiteNoise
# --------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# --------------------
# CSV directory (ensure exists, create parents)
# --------------------
CSV_EXPORT_DIR = BASE_DIR / 'csv_exports'
try:
    CSV_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # If creation fails, continue — write attempts will raise later and appear in logs
    pass

# --------------------
# Logging (console + rotating file for 'attendance' logger)
# --------------------
LOG_DIR = BASE_DIR / 'logs'
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'standard': {
            'format': '[%(asctime)s] %(levelname)s %(name)s:%(lineno)d — %(message)s'
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'stream': sys.stdout,
        },
        'attendance_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'standard',
            'filename': str(LOG_DIR / 'attendance.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 5,
            'encoding': 'utf-8',
        },
    },

    'loggers': {
        'attendance': {
            'handlers': ['attendance_file', 'console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}

# --------------------
# JWT Auth
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
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
