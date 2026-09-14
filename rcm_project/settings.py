from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent



# =========================
# Security
# =========================

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "slh*2!n6@r7a(0ap4%baua9xzt*!xuj61p!_-06mkzxu76&^ld"
)

# Render sets RENDER=true in its environment. Default DEBUG to False on Render, True locally.
DEBUG = os.environ.get("DEBUG", "False" if os.environ.get("RENDER") else "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "testserver",
    ".onrender.com",
]

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

extra_hosts = os.environ.get("ALLOWED_HOSTS")
if extra_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in extra_hosts.split(",") if h.strip()])

CSRF_TRUSTED_ORIGINS = [
    "https://*.onrender.com",
    "http://127.0.0.1",
    "http://localhost",
]

if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

extra_origins = os.environ.get("CSRF_TRUSTED_ORIGINS")
if extra_origins:
    CSRF_TRUSTED_ORIGINS.extend([o.strip() for o in extra_origins.split(",") if o.strip()])


# =========================
# Applications
# =========================

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "converter",
]



# =========================
# Middleware
# =========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =========================
# URLs / WSGI / ASGI
# =========================

ROOT_URLCONF = "rcm_project.urls"

TEMPLATES = []

WSGI_APPLICATION = "rcm_project.wsgi.application"
ASGI_APPLICATION = "rcm_project.asgi.application"


# =========================
# Database
# =========================

if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# =========================
# Internationalization
# =========================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Bangkok"

USE_I18N = True
USE_TZ = True


# =========================
# Static files
# =========================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# =========================
# Production Security
# =========================

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() == "true"
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# =========================
# Default primary key
# =========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"