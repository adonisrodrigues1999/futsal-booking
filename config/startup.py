import os
import subprocess
import sys


def main():
    subprocess.check_call([sys.executable, "manage.py", "migrate", "--noinput"])
    subprocess.check_call([sys.executable, "manage.py", "collectstatic", "--noinput"])
    subprocess.check_call([sys.executable, "manage.py", "check_email_config"])

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
    main()
