from .settings import *  # noqa: F403,F401


DEBUG = False

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
