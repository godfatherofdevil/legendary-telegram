import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_DEV_SECRET_KEY = "local-dev-secret-key"


def env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, str(int(default)))).strip().lower()
    return value in {"1", "true", "yes", "on"}


def build_channel_layers(*, redis_url: str, allow_inmemory_fallback: bool) -> dict:
    if redis_url:
        return {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {"hosts": [redis_url]},
            }
        }
    if allow_inmemory_fallback:
        return {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    raise ImproperlyConfigured(
        "REDIS_URL must be configured when in-memory channel layer fallback is disabled."
    )

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", LOCAL_DEV_SECRET_KEY)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["Accept", "Authorization", "Content-Type", "X-CSRFToken"]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    "apps.common",
    "apps.accounts",
    "apps.presence",
    "apps.social",
    "apps.chat",
    "apps.attachments",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.common.middleware.EnsureCsrfCookieMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.SessionTrackingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {"timeout": 20}

REDIS_URL = os.environ.get("REDIS_URL", "")
ALLOW_INMEMORY_CHANNEL_LAYER = DEBUG or env_bool("DJANGO_ALLOW_INMEMORY_CHANNEL_LAYER", False)
CHANNEL_LAYERS = build_channel_layers(
    redis_url=REDIS_URL,
    allow_inmemory_fallback=ALLOW_INMEMORY_CHANNEL_LAYER,
)
CHAT_PRESENCE_HEARTBEAT_TTL_SECONDS = int(
    os.environ.get("CHAT_PRESENCE_HEARTBEAT_TTL_SECONDS", "90")
)
CHAT_PRESENCE_SNAPSHOT_TTL_SECONDS = int(
    os.environ.get("CHAT_PRESENCE_SNAPSHOT_TTL_SECONDS", "120")
)
CHAT_TYPING_TTL_SECONDS = int(os.environ.get("CHAT_TYPING_TTL_SECONDS", "15"))
CHAT_MIGRATION_FLAGS = {
    "redis_presence_enabled": env_bool("CHAT_REDIS_PRESENCE_ENABLED", False),
    "redis_fanout_enabled": env_bool("CHAT_REDIS_FANOUT_ENABLED", False),
    "redis_stream_publish_enabled": env_bool("CHAT_REDIS_STREAM_PUBLISH_ENABLED", False),
    "async_persistence_enabled": env_bool("CHAT_ASYNC_PERSISTENCE_ENABLED", False),
    "legacy_sql_presence_enabled": env_bool("CHAT_LEGACY_SQL_PRESENCE_ENABLED", False),
    "legacy_sql_fanout_enabled": env_bool("CHAT_LEGACY_SQL_FANOUT_ENABLED", False),
    "stream_fallback_to_sync_sql_enabled": env_bool(
        "CHAT_STREAM_FALLBACK_TO_SYNC_SQL_ENABLED", False
    ),
    "parity_verification_enabled": env_bool("CHAT_PARITY_VERIFICATION_ENABLED", False),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "apps.common.api.custom_exception_handler",
}

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
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))
ATTACHMENTS_STORAGE_DIR = "attachments"
ATTACHMENTS_STORAGE_BACKEND = os.environ.get("ATTACHMENTS_STORAGE_BACKEND", "filesystem")
ATTACHMENTS_S3_ENDPOINT_URL = os.environ.get("ATTACHMENTS_S3_ENDPOINT_URL", "")
ATTACHMENTS_S3_BUCKET = os.environ.get("ATTACHMENTS_S3_BUCKET", "uploads")
ATTACHMENTS_S3_ACCESS_KEY_ID = os.environ.get("ATTACHMENTS_S3_ACCESS_KEY_ID", "")
ATTACHMENTS_S3_SECRET_ACCESS_KEY = os.environ.get("ATTACHMENTS_S3_SECRET_ACCESS_KEY", "")
ATTACHMENTS_S3_REGION = os.environ.get("ATTACHMENTS_S3_REGION", "us-east-1")
ATTACHMENTS_S3_USE_SSL = env_bool("ATTACHMENTS_S3_USE_SSL", False)
ATTACHMENTS_S3_VERIFY_SSL = env_bool("ATTACHMENTS_S3_VERIFY_SSL", False)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_COOKIE_AGE", 60 * 60 * 24 * 30))
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "noreply@chat.local")
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = os.environ.get("DJANGO_SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("DJANGO_CSRF_COOKIE_SAMESITE", "Lax")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env_bool("DJANGO_USE_X_FORWARDED_HOST", False)
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get("DJANGO_SECURE_REFERRER_POLICY", "same-origin")
X_FRAME_OPTIONS = os.environ.get("DJANGO_X_FRAME_OPTIONS", "DENY")
