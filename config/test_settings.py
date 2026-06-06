from .settings import *  # noqa: F403,F401


DEBUG = False

# Keep test clients on plain HTTP so assertions see real response codes instead
# of security redirects from production-only HTTPS enforcement.
SECURE_SSL_REDIRECT = False
PREPEND_WWW = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Use a local SQLite DB for repeatable test/build checks in restricted environments.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/footbook_test.sqlite3",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Avoid manifest/static pipeline strictness during test runs.
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
