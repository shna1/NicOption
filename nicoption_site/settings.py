from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_STATIC_DIR = BASE_DIR / "bambo_bot" / "web_static"
PUBLIC_SITE_ORIGIN = os.getenv("PUBLIC_SITE_ORIGIN", "https://nicoption.ir").rstrip("/")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false."
        )
    SECRET_KEY = "ni-option-local-development-key"

allowed_hosts_value = os.getenv(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost,[::1]" if DEBUG else "",
)
ALLOWED_HOSTS = [
    item.strip()
    for item in allowed_hosts_value.split(",")
    if item.strip()
]
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must be set when DJANGO_DEBUG is false."
    )
CSRF_TRUSTED_ORIGINS = [
    item.strip()
    for item in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if item.strip()
]

INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    # Project apps
    "nicoption_dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "nicoption_dashboard.middleware.VerifiedEmailRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "nicoption_site.urls"
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
    }
]

WSGI_APPLICATION = "nicoption_site.wsgi.application"
ASGI_APPLICATION = "nicoption_site.asgi.application"

database_url = os.getenv("DATABASE_URL", "").strip()
if not DEBUG and not database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL must be set when DJANGO_DEBUG is false."
    )

DATABASES = {
    "default": dj_database_url.config(
        default=database_url or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "600")),
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        )
    },
]
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("DJANGO_EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", "nicoption <no-reply@nicoption.ir>")
PASSWORD_RESET_TIMEOUT = int(os.getenv("DJANGO_EMAIL_VERIFICATION_TIMEOUT", "86400"))

ECONOMIC_GOOGLE_TIMEOUT_SECONDS = int(os.getenv("ECONOMIC_GOOGLE_TIMEOUT_SECONDS", "20"))
ECONOMIC_GOOGLE_RETRIES = int(os.getenv("ECONOMIC_GOOGLE_RETRIES", "2"))
ECONOMIC_PRICETODAY_TIMEOUT_SECONDS = int(os.getenv("ECONOMIC_PRICETODAY_TIMEOUT_SECONDS", "20"))
ECONOMIC_PRICETODAY_RETRIES = int(os.getenv("ECONOMIC_PRICETODAY_RETRIES", "2"))
ECONOMIC_FINPY_TSE_RETRIES = int(os.getenv("ECONOMIC_FINPY_TSE_RETRIES", "2"))
ECONOMIC_MAX_FUTURE_DAYS = int(os.getenv("ECONOMIC_MAX_FUTURE_DAYS", "7"))
ECONOMIC_OUTLIER_PERCENT = os.getenv("ECONOMIC_OUTLIER_PERCENT", "200")
CBI_MCP_COMMAND = os.getenv("CBI_MCP_COMMAND", "cbi-mcp")
CBI_MCP_TIMEOUT_SECONDS = int(os.getenv("CBI_MCP_TIMEOUT_SECONDS", "120"))
AMAR_MCP_COMMAND = os.getenv("AMAR_MCP_COMMAND", "amar-mcp")
AMAR_MCP_TIMEOUT_SECONDS = int(os.getenv("AMAR_MCP_TIMEOUT_SECONDS", "180"))

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [WEB_STATIC_DIR]
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
# The existing single-page interface uses root-relative /app.js, /styles.css,
# /fonts and /assets URLs. WhiteNoise serves those exact paths unchanged.
WHITENOISE_ROOT = WEB_STATIC_DIR
WHITENOISE_MAX_AGE = 0 if DEBUG else 31536000

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# Django's CSRF protection needs a same-origin Referer fallback for secure POSTs.
# `no-referrer` can turn an Admin form submission into an opaque/null origin.
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_COOKIE_AGE", "43200"))
SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
