import os
from pathlib import Path
from urllib.parse import quote_plus

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-villa-heroica-local-dev-key-2024')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'control',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'asistencia.urls'

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

WSGI_APPLICATION = 'asistencia.wsgi.application'

# Base de datos
# 1. PostgreSQL en produccion via DATABASE_URL / Railway vars
# 2. SQLite local para desarrollo
_en_nube = bool(
    os.environ.get('RAILWAY_ENVIRONMENT')
    or os.environ.get('VERCEL')
    or os.environ.get('RAILWAY_PROJECT_ID')
)


def _database_url_from_parts():
    host = os.environ.get('PGHOST') or os.environ.get('POSTGRES_HOST')
    port = os.environ.get('PGPORT') or os.environ.get('POSTGRES_PORT') or '5432'
    user = os.environ.get('PGUSER') or os.environ.get('POSTGRES_USER')
    password = os.environ.get('PGPASSWORD') or os.environ.get('POSTGRES_PASSWORD')
    name = os.environ.get('PGDATABASE') or os.environ.get('POSTGRES_DB') or os.environ.get('POSTGRES_DATABASE')

    if not all([host, port, user, password, name]):
        return ''

    return (
        f'postgresql://{quote_plus(user)}:{quote_plus(password)}@'
        f'{host}:{port}/{name}'
    )


def _resolve_database_url():
    candidates = [
        os.environ.get('DATABASE_URL', '').strip(),
        os.environ.get('DATABASE_PRIVATE_URL', '').strip(),
        os.environ.get('DATABASE_PUBLIC_URL', '').strip(),
        os.environ.get('POSTGRES_URL', '').strip(),
        os.environ.get('POSTGRES_PRIVATE_URL', '').strip(),
        os.environ.get('POSTGRES_PUBLIC_URL', '').strip(),
        _database_url_from_parts(),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return ''


_DATABASE_URL = _resolve_database_url()

if _DATABASE_URL:
    print('Using PostgreSQL production database')
    DATABASES = {
        'default': dj_database_url.parse(
            _DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
    DATABASES['default']['CONN_HEALTH_CHECKS'] = True
else:
    if _en_nube and 'collectstatic' not in os.sys.argv:
        raise ImproperlyConfigured('DATABASE_URL es obligatorio en produccion para usar PostgreSQL.')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(BASE_DIR / 'db.sqlite3'),
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# Kiosco
KIOSCO_TOLERANCIA_TARDANZA_MIN = int(os.environ.get('TOLERANCIA_TARDANZA_MIN', 20))
KIOSCO_TOLERANCIA_SALIDA_ANT_MIN = int(os.environ.get('TOLERANCIA_SALIDA_ANT_MIN', 40))
KIOSCO_BIENVENIDA_SEGUNDOS = int(os.environ.get('BIENVENIDA_SEGUNDOS', 4))
KIOSCO_IDLE_SEGUNDOS = int(os.environ.get('IDLE_SEGUNDOS', 30))

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'villa-heroica-cache',
    }
}

# Logging
_LOGS_DIR = Path('/tmp/logs') if _en_nube else BASE_DIR / 'logs'
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'timestamp': {
            'format': '{asctime} {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'timestamp',
        },
    },
    'loggers': {
        'control.asistencia': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# CSRF
CSRF_TRUSTED_ORIGINS = [
    'https://*.vercel.app',
    'https://*.railway.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
