from django.db import transaction
from .models import Slot, Booking, BookedSlot, BookingActivityLog
from datetime import timedelta, timezone
import datetime
@transaction.atomic
def create_booking(user, ground, date, start_time, hours, name, phone, source):
    slots = []
    current_time = start_time

    for _ in range(hours):
        slot = Slot.objects.select_for_update().get(
            ground=ground,
            date=date,
            start_time=current_time,
            is_booked=False
        )
        slots.append(slot)
        current_time = (datetime.combine(date, current_time) + timedelta(hours=1)).time()

    total_price = ground.get_price(start_time, hours)
    booking = Booking.objects.create(
        ground=ground,
        user=user,
        customer_name=name,
        customer_phone=phone,
        date=date,
        start_time=start_time,
        end_time=current_time,
        duration_hours=hours,
        total_amount=total_price,
        owner_payout=total_price - 3,
        booking_source=source
    )

    for s in slots:
        s.is_booked = True
        s.save()
        BookedSlot.objects.create(slot=s, booking=booking)

    BookingActivityLog.objects.create(
        booking=booking,
        action='CREATED',
        performed_by=user,
        role=user.role if user else 'OWNER'
    )

    return booking


@transaction.atomic
def cancel_booking(booking, user):
    booking.status = 'CANCELLED'
    booking.cancelled_at = timezone.now()
    booking.save()

    for bs in BookedSlot.objects.filter(booking=booking):
        bs.slot.is_booked = False
        bs.slot.save()

    BookingActivityLog.objects.create(
        booking=booking,
        action='CANCELLED',
        performed_by=user,
        role=user.role
    )
