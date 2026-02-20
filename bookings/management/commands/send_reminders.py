from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from bookings.models import Booking
from datetime import timedelta


class Command(BaseCommand):
    help = 'Send reminder emails 45 minutes before booked slot to user and owner'

    def handle(self, *args, **options):
        now = timezone.localtime(timezone.now())
        window_start = now + timedelta(minutes=44)
        window_end = now + timedelta(minutes=46)

        # Find bookings that are BOOKED, not cancelled, and reminder not sent
        candidates = Booking.objects.filter(status='BOOKED', reminder_sent=False)

        sent_count = 0
        for booking in candidates.select_related('slot__ground__owner', 'user'):
            try:
                slot = booking.slot
            except Exception:
                continue

            # Compute slot start datetime (aware)
            slot_dt = timezone.make_aware(timezone.datetime.combine(slot.date, slot.start_time), timezone.get_current_timezone())

            if window_start <= slot_dt <= window_end:
                # Prepare recipients
                recipients = []
                owner = slot.ground.owner
                if owner and owner.email:
                    recipients.append(owner.email)

                if booking.user and booking.user.email:
                    recipients.append(booking.user.email)

                # Avoid duplicate recipients
                recipients = list(set(recipients))

                if not recipients:
                    # No email recipients available; mark as sent to avoid repeated attempts
                    booking.reminder_sent = True
                    booking.save(update_fields=['reminder_sent'])
                    continue

                subject = f"Upcoming booking reminder: {slot.ground.name} at {slot.start_time.strftime('%I:%M %p')}"
                body_lines = [
                    f"Ground: {slot.ground.name}",
                    f"Date: {slot.date}",
                    f"Time: {slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}",
                    "\nThis is a reminder that the above booking starts in approximately 45 minutes.",
                    "Regards,\nFootBook",
                ]
                body = "\n".join(body_lines)
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)

                try:
                    send_mail(subject, body, from_email, recipients, fail_silently=False)
                    booking.reminder_sent = True
                    booking.save(update_fields=['reminder_sent'])
                    sent_count += 1
                except Exception as e:
                    # log error to stderr but continue
                    self.stderr.write(f"Failed to send reminder for booking {booking.id}: {e}\n")

        self.stdout.write(f"Reminders sent: {sent_count}\n")
