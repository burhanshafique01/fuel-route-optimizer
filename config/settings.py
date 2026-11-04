"""Django settings for the fuel route optimizer.

Values that differ between environments are read from environment variables
with development-friendly defaults.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me-in-production"
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "stations",
    "routes",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Geocoding and routing responses are cached on disk so repeated requests
# (and server restarts) never hit the external APIs again.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.environ.get("DJANGO_CACHE_DIR", str(BASE_DIR / ".cache")),
        "TIMEOUT": 60 * 60 * 24 * 7,
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

if "test" in sys.argv:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OpenStreetMap's tile servers reject requests without a Referer header.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# --- Fuel route optimizer -------------------------------------------------

FUEL_PRICES_CSV = BASE_DIR / "data" / "fuel-prices.csv"
CITY_GEOCODES_JSON = BASE_DIR / "data" / "city_geocodes.json"

FUEL_ROUTE = {
    "VEHICLE_RANGE_MILES": 500.0,
    "VEHICLE_MPG": 10.0,
    # Stations whose city centroid lies within this distance of the route are
    # candidates. Prices are geocoded at city level, hence a few miles of slack.
    "DEFAULT_MAX_DETOUR_MILES": 10.0,
    "MAX_ALLOWED_DETOUR_MILES": 50.0,
    "OSRM_URL": os.environ.get("OSRM_URL", "https://router.project-osrm.org"),
    "NOMINATIM_URL": os.environ.get(
        "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
    ),
    "PHOTON_URL": os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/"),
    "GEOCODER_TIMEOUT_SECONDS": 8,
    "HTTP_TIMEOUT_SECONDS": 20,
    # Outbound HTTP over IPv4 only (avoids long stalls on hosts with broken IPv6).
    "FORCE_IPV4": env_bool("FORCE_IPV4", True),
    "USER_AGENT": "fuel-route-optimizer/1.0 (assessment project)",
}
