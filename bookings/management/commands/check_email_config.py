from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Log a safe summary of the active email configuration"

    def handle(self, *args, **options):
        debug = getattr(settings, "DEBUG", False)
        backend = getattr(settings, "EMAIL_BACKEND", "unknown")
        host = getattr(settings, "EMAIL_HOST", "")
        port = getattr(settings, "EMAIL_PORT", "")
        use_tls = getattr(settings, "EMAIL_USE_TLS", False)
        sender = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        host_user_set = bool(getattr(settings, "EMAIL_HOST_USER", ""))
        host_password_set = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))

        self.stdout.write(
            "Email config: "
            f"backend={backend} "
            f"host={host} "
            f"port={port} "
            f"tls={use_tls} "
            f"debug={debug} "
            f"host_user_set={host_user_set} "
            f"host_password_set={host_password_set} "
            f"sender={sender}"
        )

        if "console.EmailBackend" in backend:
            warning = "Email backend is console; outbound mail will not be sent."
            if not debug:
                warning = "Production is using console email backend; outbound mail will not be sent."
            self.stdout.write(self.style.WARNING(warning))
            if not debug:
                raise CommandError(warning)
        elif not host_password_set:
            warning = "EMAIL_HOST_PASSWORD is empty; SMTP sends will fail."
            if not debug:
                warning = "Production EMAIL_HOST_PASSWORD is empty; SMTP sends will fail."
            self.stdout.write(self.style.WARNING(warning))
            if not debug:
                raise CommandError(warning)
