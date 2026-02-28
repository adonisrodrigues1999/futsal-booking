from django.core.management.base import BaseCommand
from django.db import transaction

from bookings.models import Booking, Slot


class Command(BaseCommand):
    help = (
        "Delete all bookings and mark all slots as unbooked. "
        "Users, owners, and grounds are not modified."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required flag to execute deletion.",
        )

    def handle(self, *args, **options):
        if not options.get("confirm"):
            self.stdout.write(self.style.WARNING("Dry run only."))
            self.stdout.write(
                "This will delete all rows from bookings_booking and reopen all slots."
            )
            self.stdout.write(
                self.style.WARNING(
                    "Re-run with: python manage.py clear_bookings --confirm"
                )
            )
            return

        with transaction.atomic():
            booking_count = Booking.objects.count()
            slot_reopen_count = Slot.objects.filter(is_booked=True).update(is_booked=False)
            Booking.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Booking reset completed."))
        self.stdout.write(f"Deleted bookings: {booking_count}")
        self.stdout.write(f"Reopened slots: {slot_reopen_count}")
