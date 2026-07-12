import os

from django.core.management import call_command
from django.core.management.base import CommandError


def main():
    call_command("migrate", "--noinput")
    call_command("collectstatic", "--noinput")
    call_command("check_email_config")

    port = os.getenv("PORT", "8000")
    os.execvp(
        "gunicorn",
        [
            "gunicorn",
            "config.wsgi:application",
            "--bind",
            f"0.0.0.0:{port}",
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except CommandError:
        raise
