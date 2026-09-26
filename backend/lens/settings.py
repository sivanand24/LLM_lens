"""Django settings for LLM Lens.

No SQL database: all persistence goes through pymongo (see core.db).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "core",
    "proxy",
    "checks.apps.ChecksConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "lens.urls"
WSGI_APPLICATION = "lens.wsgi.application"
APPEND_SLASH = False

# pymongo only — Django's ORM is unused.
DATABASES = {}

USE_TZ = True
TIME_ZONE = "UTC"

CORS_ALLOWED_ORIGINS = ["http://localhost:4200", "http://127.0.0.1:4200"]
CORS_ALLOW_HEADERS = ["content-type", "x-llm-lens-key"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

# --- LLM Lens ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "llm_lens")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
USE_MOCK = env_bool("USE_MOCK", False)

LENS_API_KEY = os.getenv("LENS_API_KEY", "dev-key")
DRIFT_INTERVAL_SECS = int(os.getenv("DRIFT_INTERVAL_SECS", "300"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
