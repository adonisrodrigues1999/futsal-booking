from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, timedelta
from django.db import transaction, OperationalError, IntegrityError
import time
from django.core.mail import send_mail
from django.conf import settings

from .models import Ground, Slot, Booking, ActivityLog
from .slot_generation import ensure_slots_for_ground_date


def _slot_start_datetime(slot):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(
        datetime.combine(slot.date, slot.start_time),
        tz
    )


@login_required
def home(request):
    user = request.user

    if user.role == 'admin':
        return redirect('admin_dashboard')
    elif user.role == 'owner':
        return redirect('owner_dashboard')

    return render(request, 'dashboard/customer_home.html')


@login_required
def ground_list(request):
    grounds = Ground.objects.all()
    return render(request, 'grounds/ground_list.html', {
        'grounds': grounds
    })


@login_required
def ground_slots(request, ground_id):
    ground = get_object_or_404(Ground, id=ground_id)
    # date navigation: ?date=YYYY-MM-DD
    date_str = request.GET.get('date')
    try:
        if date_str:
            selected_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            selected_date = timezone.localdate()
    except Exception:
        selected_date = timezone.localdate()

    # Ensure slots exist for the selected date
    ensure_slots_for_ground_date(ground=ground, slot_date=selected_date)

    # fetch slots for that date
    slots_qs = Slot.objects.filter(ground=ground, date=selected_date).order_by('start_time')

    visible_slots = []
    now_dt = timezone.localtime(timezone.now())
    today = timezone.localdate()
    for slot in slots_qs:
        # Skip slots outside operating hours
        if ground.closing_time > ground.opening_time:
            # Normal hours
            if slot.start_time < ground.opening_time or slot.start_time >= ground.closing_time:
                continue
        else:
            # Overnight hours
            if not (slot.start_time >= ground.opening_time or slot.start_time < ground.closing_time):
                continue

        # if selected date is today, hide slots that have already started
        slot_dt = timezone.make_aware(timezone.datetime.combine(selected_date, slot.start_time), timezone.get_current_timezone())
        is_past = slot_dt <= now_dt

        # Check if there's an active booking for this slot
        booking = Booking.objects.filter(slot=slot, status='BOOKED').first()
        user_booking = (booking.user == request.user) if booking else False
        can_cancel = False
        cancel_no_refund = False
        if booking and user_booking:
            can_cancel = slot.date >= today
            if can_cancel:
                hours_to_slot = (_slot_start_datetime(slot) - now_dt).total_seconds() / 3600
                cancel_no_refund = hours_to_slot < 4

        visible_slots.append({
            'slot': slot,
            'is_past': is_past,
            'price': ground.day_price if 6 <= slot.start_time.hour < 18 else ground.night_price,
            'booking': booking,
            'user_booking': user_booking,
            'can_cancel': can_cancel,
            'cancel_no_refund': cancel_no_refund,
        })

    prev_date = selected_date - timezone.timedelta(days=1)
    next_date = selected_date + timezone.timedelta(days=1)

    if prev_date < timezone.localdate():
        prev_date = None

    return render(request, 'bookings/slots.html', {
        'ground': ground,
        'slots': visible_slots,
        'selected_date': selected_date,
        'prev_date': prev_date,
        'next_date': next_date,
    })


@login_required
def book_slot(request, slot_id):
    slot = get_object_or_404(Slot, id=slot_id)

    # Check daily booking limit per ground
    existing_bookings = Booking.objects.filter(
        user=request.user,
        slot__ground=slot.ground,
        slot__date=slot.date,
        status='BOOKED'
    ).count()
    if existing_bookings >= 5:
        messages.error(request, 'You can only book up to 5 slots per day per ground.')
        return redirect(f'/grounds/{slot.ground.id}/?date={slot.date}')

    # perform booking inside a short transaction; retry on transient DB locks (SQLite)
    attempts = 3
    for attempt in range(attempts):
        try:
            with transaction.atomic():
                slot = Slot.objects.select_for_update().get(id=slot_id)

                if slot.is_booked or Booking.objects.filter(slot=slot, status='BOOKED').exists():
                    messages.error(request, 'Slot is already booked.')
                    return redirect(f'/grounds/{slot.ground.id}/?date={slot.date}')

                # Calculate total amount based on time of day
                hour = slot.start_time.hour
                if 6 <= hour < 18:  # Day pricing
                    price_per_hour = slot.ground.day_price
                else:  # Night pricing
                    price_per_hour = slot.ground.night_price

                total_amount = price_per_hour  # For 1 hour booking
                owner_payout = total_amount - 3  # Platform fee is 3

                booking = Booking.objects.create(
                    user=request.user,
                    slot=slot,
                    customer_name=request.user.name,
                    customer_phone=request.user.phone_number,
                    total_amount=total_amount,
                    owner_payout=owner_payout,
                    booking_source='ONLINE'
                )

                slot.is_booked = True
                slot.save()

                ActivityLog.objects.create(
                    user=request.user,
                    action='BOOKED',
                    booking=booking,
                    slot=slot
                )

                # notify ground owner by email (non-blocking)
                try:
                    owner = slot.ground.owner
                    if owner and owner.email:
                        subject = f"New booking: {slot.ground.name} on {slot.date} {slot.start_time.strftime('%I:%M %p')}"
                        body = (
                            f"Hello {owner.name},\n\n"
                            f"A new booking was made for your ground {slot.ground.name}.\n"
                            f"Date: {slot.date}\n"
                            f"Time: {slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}\n"
                            f"Booked by: {request.user.name} ({request.user.email if request.user.email else request.user.phone_number})\n\n"
                            "Regards,\nFootBook"
                        )
                        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
                        send_mail(subject, body, from_email, [owner.email], fail_silently=True)
                except Exception:
                    pass

                messages.success(request, f'Slot booked successfully for {slot.start_time.strftime("%I:%M %p")} - {slot.end_time.strftime("%I:%M %p")} on {slot.date}.')

                return redirect('/my-bookings/')
        except OperationalError:
            # retry on transient DB lock
            if attempt < attempts - 1:
                time.sleep(0.1)
                continue
            messages.error(request, 'Database is busy, please try again.')
            return redirect(f'/grounds/{slot.ground.id}/?date={slot.date}')
        except IntegrityError:
            messages.error(request, 'Unable to create booking, please try again.')
            return redirect(f'/grounds/{slot.ground.id}/?date={slot.date}')

    messages.error(request, 'Unable to book slot right now.')
    return redirect('/grounds/')


@login_required
def my_bookings(request):
    # show only active (BOOKED) bookings for the current user
    bookings = Booking.objects.filter(user=request.user, status='BOOKED').order_by('-created_at')
    now_dt = timezone.localtime(timezone.now())
    today = timezone.localdate()

    # Group by date
    bookings_by_date = {}
    for booking in bookings:
        slot_start = _slot_start_datetime(booking.slot)
        booking.can_cancel = booking.slot.date >= today
        booking.cancel_no_refund = booking.can_cancel and ((slot_start - now_dt).total_seconds() / 3600) < 4

        date = booking.slot.date
        if date not in bookings_by_date:
            bookings_by_date[date] = []
        bookings_by_date[date].append(booking)

    return render(request, 'bookings/my_bookings.html', {
        'bookings_by_date': bookings_by_date
    })


@login_required
def owner_dashboard(request):
    owner = request.user
    grounds = Ground.objects.filter(owner=owner)

    bookings = Booking.objects.filter(slot__ground__in=grounds, status='BOOKED')

    # heatmap by hour
    heatmap = {}
    for b in bookings:
        hour = b.slot.start_time.hour
        heatmap[hour] = heatmap.get(hour, 0) + 1

    # bookings per day for the last 14 days
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    labels = [d.strftime('%Y-%m-%d') for d in days]
    counts = [bookings.filter(slot__date=d).count() for d in days]

    now_dt = timezone.localtime(timezone.now())
    owner_bookings = bookings.order_by('-slot__date', '-slot__start_time')[:50]
    for booking in owner_bookings:
        booking.can_owner_cancel = _slot_start_datetime(booking.slot) > now_dt

    context = {
        'stats': {
            'total_bookings': bookings.count(),
            'revenue': bookings.count() * 1000,  # sample
            'peak_hour': max(heatmap, key=heatmap.get) if heatmap else 'N/A',
            'active_grounds': grounds.count(),
        },
        'heatmap': heatmap,
        'heatmap_labels': [i for i in range(24)],
        'heatmap_data': [heatmap.get(i, 0) for i in range(24)],
        'chart_labels': labels,
        'chart_data': counts,
        'owner_bookings': owner_bookings,
    }

    return render(request, 'dashboard/owner_dashboard.html', context)


def latest_notification(request):
    last = (
        ActivityLog.objects
        .filter(action__in=['BOOKED', 'MANUAL_BOOKING'], slot__isnull=False)
        .order_by('-timestamp')
        .first()
    )

    if not last:
        return JsonResponse(None, safe=False)

    return JsonResponse({
        'event_id': str(last.id),
        'ground': last.slot.ground.name,
        'time': last.timestamp.strftime('%H:%M')
    })



@login_required
def owner_manual_booking(request):
    owner = request.user
    grounds = Ground.objects.filter(owner=owner)
    # GET: optional filters 'ground' (id) and 'date' (YYYY-MM-DD)
    selected_ground = None
    selected_date = None
    slots = []

    if request.method == 'POST':
        # creating a manual booking
        slot_id = request.POST['slot']
        name = request.POST['name']
        phone = request.POST['phone']

        try:
            with transaction.atomic():
                slot = Slot.objects.select_for_update().get(id=slot_id, ground__owner=owner)

                if slot.is_booked or Booking.objects.filter(slot=slot, status='BOOKED').exists():
                    messages.error(request, 'Slot already booked')
                    return redirect('/dashboard/owner/')

                # Calculate amount
                hour = slot.start_time.hour
                price_per_hour = slot.ground.day_price if 6 <= hour < 18 else slot.ground.night_price
                total_amount = price_per_hour
                owner_payout = total_amount - 3

                booking = Booking.objects.create(
                    slot=slot,
                    customer_name=name,
                    customer_phone=phone,
                    total_amount=total_amount,
                    owner_payout=owner_payout,
                    booking_source='MANUAL'
                )

                slot.is_booked = True
                slot.save(update_fields=['is_booked'])

                ActivityLog.objects.create(
                    user=request.user,
                    action='MANUAL_BOOKING',
                    booking=booking,
                    slot=slot
                )
        except Slot.DoesNotExist:
            messages.error(request, 'Invalid slot selected.')
            return redirect('/owner/manual-booking/')

        messages.success(request, 'Manual booking created')
        return redirect('/dashboard/owner/')

    # GET handling: filter slots if ground+date provided
    ground_id = request.GET.get('ground')
    date_str = request.GET.get('date')
    if ground_id:
        try:
            selected_ground = Ground.objects.get(id=ground_id, owner=owner)
        except Ground.DoesNotExist:
            selected_ground = None

    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            selected_date = None

    if selected_ground and selected_date:
        slots_qs = Slot.objects.filter(ground=selected_ground, date=selected_date, is_booked=False).order_by('start_time')
        for s in slots_qs:
            price = s.ground.day_price if 6 <= s.start_time.hour < 18 else s.ground.night_price
            slots.append({'slot': s, 'price': price})
    else:
        # default: show all available upcoming slots across grounds owned by this owner
        slots_qs = Slot.objects.filter(ground__in=grounds, is_booked=False, date__gte=timezone.localdate()).order_by('date', 'start_time')
        for s in slots_qs:
            price = s.ground.day_price if 6 <= s.start_time.hour < 18 else s.ground.night_price
            slots.append({'slot': s, 'price': price})

    return render(request, 'owner/manual_booking.html', {
        'grounds': grounds,
        'slots': slots,
        'selected_ground': selected_ground,
        'selected_date': selected_date,
    })
    
@login_required
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.user != request.user:
        return redirect('/')

    if booking.booking_source == 'MANUAL':
        return redirect('/')

    slot = booking.slot
    today = timezone.localdate()
    if slot.date < today:
        messages.error(request, 'Past bookings cannot be cancelled.')
        return redirect('/my-bookings/')

    now_dt = timezone.localtime(timezone.now())
    slot_start = _slot_start_datetime(slot)
    no_refund = ((slot_start - now_dt).total_seconds() / 3600) < 4

    booking.status = 'CANCELLED'
    booking.cancelled_at = timezone.now()
    booking.save()

    slot.is_booked = False
    slot.save()

    ActivityLog.objects.create(
        user=request.user,
        action='CUSTOMER_CANCELLED',
        booking=booking,
        slot=slot
    )

    if no_refund:
        messages.warning(request, 'Booking cancelled.  the amount will not be refunded.')
    else:
        messages.success(request, 'Booking cancelled successfully.')

    return redirect('/my-bookings/')


@login_required
def owner_cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.slot.ground.owner != request.user:
        return redirect('/')

    slot = booking.slot
    slot_start = _slot_start_datetime(slot)
    if slot_start <= timezone.localtime(timezone.now()):
        messages.error(
            request,
            f'Cannot cancel past booking: {slot.ground.name} on {slot.date} '
            f'({slot.start_time.strftime("%I:%M %p")} - {slot.end_time.strftime("%I:%M %p")}).'
        )
        return redirect('/dashboard/owner/')

    booking.status = 'CANCELLED'
    booking.cancelled_at = timezone.now()
    booking.save()

    slot.is_booked = False
    slot.save()

    ActivityLog.objects.create(
        user=request.user,
        action='OWNER_CANCELLED',
        booking=booking,
        slot=slot
    )

    messages.success(
        request,
        f'Booking deleted: {slot.ground.name} on {slot.date} '
        f'({slot.start_time.strftime("%I:%M %p")} - {slot.end_time.strftime("%I:%M %p")}) '
        f'for {booking.customer_name} ({booking.customer_phone}).'
    )

    return redirect('/dashboard/owner/')
