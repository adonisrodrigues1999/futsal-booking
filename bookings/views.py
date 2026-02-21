from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime, timedelta
from django.db import transaction, OperationalError, IntegrityError
import time
from django.core.mail import send_mail
from django.conf import settings
import csv
import io
import json
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt

try:
    import stripe
except Exception:
    stripe = None

try:
    import razorpay
except Exception:
    razorpay = None

from .models import Ground, Slot, Booking, ActivityLog
from .slot_generation import ensure_slots_for_ground_date
import os
from django.http import FileResponse, Http404
from django.conf import settings as djsettings


def _slot_start_datetime(slot):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(
        datetime.combine(slot.date, slot.start_time),
        tz
    )


def _is_day_slot(slot_time):
    return 6 <= slot_time.hour < 18


def _slot_price(ground, slot_time):
    return ground.day_price if _is_day_slot(slot_time) else ground.night_price


def _payment_amounts(total_amount, payment_mode):
    if payment_mode == 'PARTIAL_99':
        paid = 99
        due = max(total_amount - paid, 0)
        if due <= 0:
            return total_amount, 0, 'FULL'
        return paid, due, 'PARTIAL_99'
    return total_amount, 0, 'FULL'


def _is_restricted_manual_hour(slot_time):
    return 2 <= slot_time.hour < 6


def _owner_booking_email(booking):
    owner = booking.slot.ground.owner if booking.slot and booking.slot.ground else None
    if not owner or not owner.email:
        return

    payment_time = timezone.localtime(booking.payment_paid_at).strftime('%Y-%m-%d %I:%M %p') if booking.payment_paid_at else '-'
    subject = f"New booking payment: {booking.slot.ground.name} on {booking.slot.date} {booking.slot.start_time.strftime('%I:%M %p')}"
    body = (
        f"Hello {owner.name},\n\n"
        f"A new booking was confirmed for your ground {booking.slot.ground.name}.\n"
        f"Date: {booking.slot.date}\n"
        f"Time: {booking.slot.start_time.strftime('%I:%M %p')} - {booking.slot.end_time.strftime('%I:%M %p')}\n"
        f"Customer: {booking.customer_name} ({booking.customer_phone})\n\n"
        f"Payment details:\n"
        f"- Mode: {booking.get_payment_mode_display()}\n"
        f"- Status: {booking.get_payment_status_display()}\n"
        f"- Paid: ₹{booking.paid_amount}\n"
        f"- Due: ₹{booking.due_amount}\n"
        f"- Payment Time: {payment_time}\n"
        f"- Booking Policy: Non-refundable\n\n"
        "Regards,\nFootBook"
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
    send_mail(subject, body, from_email, [owner.email], fail_silently=True)


def _razorpay_client():
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    if not key_id or not key_secret or razorpay is None:
        return None, key_id
    return razorpay.Client(auth=(key_id, key_secret)), key_id


def _operating_window_for_date(ground, target_date):
    tz = timezone.get_current_timezone()
    window_start = timezone.make_aware(
        datetime.combine(target_date, ground.opening_time),
        tz,
    )
    window_end_date = target_date
    if ground.closing_time <= ground.opening_time:
        window_end_date = target_date + timedelta(days=1)
    window_end = timezone.make_aware(
        datetime.combine(window_end_date, ground.closing_time),
        tz,
    )
    return window_start, window_end


def ground_image(request, ground_id):
    # Serve a ground image from the project `groundsimages` folder if available.
    try:
        ground = Ground.objects.get(id=ground_id)
    except Ground.DoesNotExist:
        raise Http404()

    # If ground.image is set and looks like a URL/path, try to serve it directly
    if ground.image:
        # If it's an absolute filesystem path, serve it
        if os.path.isabs(ground.image) and os.path.exists(ground.image):
            return FileResponse(open(ground.image, 'rb'))
        # If it looks like a relative static path (starts with / or without scheme), try to serve from BASE_DIR
        rel_path = os.path.join(djsettings.BASE_DIR, ground.image.lstrip('/'))
        if os.path.exists(rel_path):
            return FileResponse(open(rel_path, 'rb'))

    # Special-case: look in project `groundsimages` directory for a matching file
    images_dir = os.path.join(djsettings.BASE_DIR, 'groundsimages')
    if os.path.isdir(images_dir):
        # Try exact filename mapping for known grounds
        special_map = {
            'Simpliz Turf': 'simplisturf.webp',
        }
        fname = special_map.get(ground.name)
        if fname:
            full = os.path.join(images_dir, fname)
            if os.path.exists(full):
                return FileResponse(open(full, 'rb'))

        # fallback: try any file in the folder that contains the ground name (normalized)
        norm = ''.join(ch for ch in ground.name.lower() if ch.isalnum())
        for f in os.listdir(images_dir):
            if norm in ''.join(ch for ch in f.lower() if ch.isalnum()):
                return FileResponse(open(os.path.join(images_dir, f), 'rb'))

    # Not found
    raise Http404()


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
    window_start, window_end = _operating_window_for_date(ground, selected_date)
    for slot in slots_qs:
        slot_dt = _slot_start_datetime(slot)
        if not (window_start <= slot_dt < window_end):
            continue

        # Hide slots that have already started.
        is_past = slot_dt <= now_dt
        if is_past:
            continue

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
            'price': _slot_price(ground, slot.start_time),
            'time_icon': '☀️' if _is_day_slot(slot.start_time) else '🌙',
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
    messages.info(request, 'Online slot booking now requires payment checkout. Please book from the slot payment modal.')
    return redirect(f'/grounds/{slot.ground.id}/?date={slot.date}')


@login_required
def create_razorpay_order(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    slot_id = payload.get('slot_id')
    payment_mode = payload.get('payment_mode') or 'FULL'
    if payment_mode not in {'FULL', 'PARTIAL_99'}:
        return JsonResponse({'success': False, 'error': 'Invalid payment mode'}, status=400)

    slot = get_object_or_404(Slot, id=slot_id)
    now_dt = timezone.localtime(timezone.now())
    if _slot_start_datetime(slot) <= now_dt:
        return JsonResponse({'success': False, 'error': 'Slot has already started'}, status=400)

    if slot.is_booked or Booking.objects.filter(slot=slot, status='BOOKED').exists():
        return JsonResponse({'success': False, 'error': 'Slot is already booked'}, status=409)

    existing_bookings = Booking.objects.filter(
        user=request.user,
        slot__ground=slot.ground,
        slot__date=slot.date,
        status='BOOKED'
    ).count()
    if existing_bookings >= 5:
        return JsonResponse({'success': False, 'error': 'You can only book up to 5 slots per day per ground.'}, status=400)

    total_amount = _slot_price(slot.ground, slot.start_time)
    pay_now_amount, due_amount, resolved_mode = _payment_amounts(total_amount, payment_mode)

    client, key_id = _razorpay_client()
    if not client or not key_id:
        return JsonResponse({'success': False, 'error': 'Razorpay is not configured on server'}, status=500)

    try:
        order = client.order.create({
            'amount': pay_now_amount * 100,
            'currency': 'INR',
            'payment_capture': 1,
            'notes': {
                'slot_id': str(slot.id),
                'user_id': str(request.user.id),
                'payment_mode': resolved_mode,
            }
        })
    except Exception:
        return JsonResponse({'success': False, 'error': 'Unable to initialize payment right now'}, status=500)

    return JsonResponse({
        'success': True,
        'order_id': order.get('id'),
        'key_id': key_id,
        'slot_id': slot.id,
        'payment_mode': resolved_mode,
        'total_amount': total_amount,
        'pay_now_amount': pay_now_amount,
        'due_amount': due_amount,
        'currency': 'INR',
        'non_refundable': True,
        'prefill': {
            'name': request.user.name,
            'email': request.user.email or '',
            'contact': request.user.phone_number or '',
        },
    })


@login_required
def verify_razorpay_payment_and_book(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        payload = {}

    slot_id = payload.get('slot_id')
    payment_mode = payload.get('payment_mode') or 'FULL'
    razorpay_order_id = payload.get('razorpay_order_id')
    razorpay_payment_id = payload.get('razorpay_payment_id')
    razorpay_signature = payload.get('razorpay_signature')

    if payment_mode not in {'FULL', 'PARTIAL_99'}:
        return JsonResponse({'success': False, 'error': 'Invalid payment mode'}, status=400)
    if not (slot_id and razorpay_order_id and razorpay_payment_id and razorpay_signature):
        return JsonResponse({'success': False, 'error': 'Missing payment details'}, status=400)

    client, _ = _razorpay_client()
    if not client:
        return JsonResponse({'success': False, 'error': 'Razorpay is not configured on server'}, status=500)

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
        order = client.order.fetch(razorpay_order_id)
        payment = client.payment.fetch(razorpay_payment_id)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Payment verification failed'}, status=400)

    if str(payment.get('order_id')) != str(razorpay_order_id):
        return JsonResponse({'success': False, 'error': 'Payment/order mismatch'}, status=400)
    if payment.get('status') not in {'captured', 'authorized'}:
        return JsonResponse({'success': False, 'error': 'Payment is not captured'}, status=400)
    order_notes = order.get('notes') or {}
    if str(order_notes.get('slot_id')) != str(slot_id):
        return JsonResponse({'success': False, 'error': 'Slot mismatch for payment'}, status=400)
    if str(order_notes.get('user_id')) != str(request.user.id):
        return JsonResponse({'success': False, 'error': 'User mismatch for payment'}, status=400)

    attempts = 3
    for attempt in range(attempts):
        try:
            with transaction.atomic():
                slot = Slot.objects.select_for_update().get(id=slot_id)
                if slot.is_booked or Booking.objects.filter(slot=slot, status='BOOKED').exists():
                    return JsonResponse({'success': False, 'error': 'Slot was booked by someone else. Payment is non-refundable; contact support.'}, status=409)

                if _slot_start_datetime(slot) <= timezone.localtime(timezone.now()):
                    return JsonResponse({'success': False, 'error': 'Slot has already started'}, status=400)

                existing_bookings = Booking.objects.filter(
                    user=request.user,
                    slot__ground=slot.ground,
                    slot__date=slot.date,
                    status='BOOKED'
                ).count()
                if existing_bookings >= 5:
                    return JsonResponse({'success': False, 'error': 'You can only book up to 5 slots per day per ground.'}, status=400)

                total_amount = _slot_price(slot.ground, slot.start_time)
                paid_amount, due_amount, resolved_mode = _payment_amounts(total_amount, payment_mode)
                expected_amount_paise = paid_amount * 100
                if int(payment.get('amount') or 0) != expected_amount_paise:
                    return JsonResponse({'success': False, 'error': 'Paid amount mismatch'}, status=400)

                owner_payout = total_amount - 3
                payment_status = 'PAID' if due_amount == 0 else 'PARTIALLY_PAID'
                booking = Booking.objects.create(
                    user=request.user,
                    slot=slot,
                    customer_name=request.user.name,
                    customer_phone=request.user.phone_number,
                    total_amount=total_amount,
                    owner_payout=owner_payout,
                    booking_source='ONLINE',
                    payment_mode=resolved_mode,
                    payment_status=payment_status,
                    paid_amount=paid_amount,
                    due_amount=due_amount,
                    payment_paid_at=timezone.now(),
                    razorpay_order_id=razorpay_order_id,
                    razorpay_payment_id=razorpay_payment_id,
                    razorpay_signature=razorpay_signature,
                )

                slot.is_booked = True
                slot.save(update_fields=['is_booked'])

                ActivityLog.objects.create(
                    user=request.user,
                    action='BOOKED',
                    booking=booking,
                    slot=slot
                )

                try:
                    _owner_booking_email(booking)
                except Exception:
                    pass

                return JsonResponse({
                    'success': True,
                    'booking_id': str(booking.id),
                    'redirect_url': '/my-bookings/',
                    'message': 'Booking confirmed. Amount paid is non-refundable.',
                })
        except OperationalError:
            if attempt < attempts - 1:
                time.sleep(0.1)
                continue
            return JsonResponse({'success': False, 'error': 'Database busy, please retry.'}, status=500)
        except IntegrityError:
            return JsonResponse({'success': False, 'error': 'Unable to create booking, please retry.'}, status=500)

    return JsonResponse({'success': False, 'error': 'Unable to complete booking'}, status=500)


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
def mark_invoice_paid(request):
    # Mark invoice paid via AJAX POST
    if request.method != 'POST' or request.user.role != 'admin':
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    inv_id = request.POST.get('invoice_id')
    if not inv_id:
        return JsonResponse({'success': False, 'error': 'Missing invoice_id'}, status=400)

    from .models import GroundInvoice
    try:
        inv = GroundInvoice.objects.get(id=inv_id)
        inv.is_paid = True
        inv.save(update_fields=['is_paid'])
        return JsonResponse({'success': True, 'invoice_id': str(inv.id)})
    except GroundInvoice.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invoice not found'}, status=404)


@login_required
def mark_invoice_unpaid(request):
    # Mark invoice unpaid via AJAX POST (undo)
    if request.method != 'POST' or request.user.role != 'admin':
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    inv_id = request.POST.get('invoice_id')
    if not inv_id:
        return JsonResponse({'success': False, 'error': 'Missing invoice_id'}, status=400)

    from .models import GroundInvoice
    try:
        inv = GroundInvoice.objects.get(id=inv_id)
        inv.is_paid = False
        inv.save(update_fields=['is_paid'])
        return JsonResponse({'success': True, 'invoice_id': str(inv.id)})
    except GroundInvoice.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invoice not found'}, status=404)


@login_required
def export_invoices_csv(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    start = request.GET.get('start')
    end = request.GET.get('end')
    qs = None
    from .models import GroundInvoice
    try:
        if start and end:
            qs = GroundInvoice.objects.filter(period_start__gte=start, period_end__lte=end)
        else:
            qs = GroundInvoice.objects.all()
    except Exception:
        qs = GroundInvoice.objects.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Ground', 'Period Start', 'Period End', 'Bookings', 'Charge Per Booking', 'Total', 'Paid', 'Created At'])
    for inv in qs.order_by('-created_at'):
        writer.writerow([
            inv.ground.name,
            inv.period_start,
            inv.period_end,
            inv.bookings_count,
            f"{inv.charge_per_booking}",
            f"{inv.total_amount}",
            'Yes' if inv.is_paid else 'No',
            inv.created_at,
        ])

    resp = HttpResponse(output.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="ground_invoices.csv"'
    return resp


@login_required
def export_bookings_csv(request):
    # Export bookings CSV per-ground for a date range (admin only)
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    ground_id = request.GET.get('ground_id')
    start = request.GET.get('start')
    end = request.GET.get('end')

    qs = Booking.objects.select_related('slot__ground', 'user')
    if ground_id:
        qs = qs.filter(slot__ground__id=ground_id)
    if start:
        qs = qs.filter(slot__date__gte=start)
    if end:
        qs = qs.filter(slot__date__lte=end)

    qs = qs.order_by('-slot__date', '-slot__start_time')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Booking ID', 'Ground', 'Date', 'Start', 'End', 'Customer Name', 'Customer Phone', 'User Email', 'Amount', 'Status'])
    for b in qs:
        writer.writerow([
            str(b.id),
            b.slot.ground.name if b.slot and b.slot.ground else '',
            b.slot.date if b.slot else '',
            b.slot.start_time.strftime('%H:%M') if b.slot else '',
            b.slot.end_time.strftime('%H:%M') if b.slot else '',
            b.customer_name,
            b.customer_phone,
            b.user.email if b.user and getattr(b.user, 'email', None) else '',
            f"{b.total_amount}",
            b.status,
        ])

    resp = HttpResponse(output.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="bookings.csv"'
    return resp


@login_required
def pay_invoice(request, invoice_id):
    # Initiate Stripe Checkout for an invoice (if configured). Admin-only for now.
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    from .models import GroundInvoice
    inv = get_object_or_404(GroundInvoice, id=invoice_id)

    if inv.is_paid:
        messages.info(request, 'Invoice already paid.')
        return redirect('admin_invoices')

    # Require stripe and secret key
    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    stripe_pub = getattr(settings, 'STRIPE_PUBLIC_KEY', None)
    currency = getattr(settings, 'STRIPE_CURRENCY', 'inr')

    if stripe is None or not stripe_key:
        messages.error(request, 'Stripe is not configured. Configure STRIPE_SECRET_KEY to enable payments.')
        return redirect('admin_invoices')

    stripe.api_key = stripe_key

    # Stripe requires amount in smallest currency unit (paise for INR)
    amount = int((Decimal(inv.total_amount) * 100).quantize(Decimal('1')))

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency,
                    'product_data': {'name': f'Invoice {inv.ground.name} {inv.period_start} - {inv.period_end}'},
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.build_absolute_uri('/') + '?paid=1',
            cancel_url=request.build_absolute_uri('/') + '?paid=0',
            metadata={'invoice_id': str(inv.id)}
        )
        return redirect(session.url)
    except Exception as e:
        messages.error(request, f'Failed to create Stripe session: {e}')
        return redirect('admin_invoices')


def stripe_webhook(request):
    # Basic webhook handler to mark invoice paid when payment succeeds
    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
    if stripe is None or not stripe_key or not webhook_secret:
        return HttpResponse(status=400)

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        invoice_id = session.get('metadata', {}).get('invoice_id')
        if invoice_id:
            from .models import GroundInvoice
            try:
                inv = GroundInvoice.objects.get(id=invoice_id)
                inv.is_paid = True
                inv.save(update_fields=['is_paid'])
            except GroundInvoice.DoesNotExist:
                pass

    return HttpResponse(status=200)


@csrf_exempt
def razorpay_webhook(request):
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None)
    if request.method != 'POST' or not webhook_secret:
        return HttpResponse(status=400)

    signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
    if not signature:
        return HttpResponse(status=400)

    client, _ = _razorpay_client()
    if not client:
        return HttpResponse(status=400)

    payload = request.body.decode('utf-8')
    try:
        client.utility.verify_webhook_signature(payload, signature, webhook_secret)
        event = json.loads(payload)
    except Exception:
        return HttpResponse(status=400)

    event_name = event.get('event')
    payment_entity = (event.get('payload') or {}).get('payment', {}).get('entity', {})
    payment_id = payment_entity.get('id')
    order_id = payment_entity.get('order_id')

    if event_name in {'payment.captured', 'order.paid'} and payment_id:
        booking = (
            Booking.objects
            .filter(razorpay_payment_id=payment_id)
            .order_by('-created_at')
            .first()
        )
        if not booking and order_id:
            booking = (
                Booking.objects
                .filter(razorpay_order_id=order_id)
                .order_by('-created_at')
                .first()
            )
        if booking:
            if booking.due_amount > 0:
                booking.payment_status = 'PARTIALLY_PAID'
            else:
                booking.payment_status = 'PAID'
            if not booking.payment_paid_at:
                booking.payment_paid_at = timezone.now()
            booking.save(update_fields=['payment_status', 'payment_paid_at'])

    return HttpResponse(status=200)



@login_required
def admin_invoices(request):
    # Admin-only: show bookings per ground for a date range and create invoices
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    from django.db.models import Count
    from .models import GroundInvoice

    # date range inputs
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    try:
        if start_str:
            start_date = timezone.datetime.strptime(start_str, '%Y-%m-%d').date()
        else:
            # default to first day of current month
            today = timezone.localdate()
            start_date = today.replace(day=1)
    except Exception:
        start_date = timezone.localdate().replace(day=1)

    try:
        if end_str:
            end_date = timezone.datetime.strptime(end_str, '%Y-%m-%d').date()
        else:
            # default to today
            end_date = timezone.localdate()
    except Exception:
        end_date = timezone.localdate()

    # Aggregate bookings per ground where slot.date between start and end
    qs = Booking.objects.filter(status='BOOKED', slot__date__gte=start_date, slot__date__lte=end_date)
    counts = qs.values('slot__ground').annotate(count=Count('id')).order_by('-count')

    # Map ground id -> count
    ground_counts = {}
    for row in counts:
        ground_counts[row['slot__ground']] = row['count']

    # Get all grounds referenced in the system
    from grounds.models import Ground
    grounds = Ground.objects.all().order_by('name')

    # Pre-select ground if provided via GET (e.g. ?ground=3)
    selected_ground = None
    gparam = request.GET.get('ground')
    if gparam:
        try:
            selected_ground = int(gparam)
        except Exception:
            selected_ground = None

    # Prepare invoice creation
    if request.method == 'POST':
        ground_id = request.POST.get('ground_id')
        charge = request.POST.get('charge_per_booking')
        gstart = request.POST.get('period_start')
        gend = request.POST.get('period_end')
        try:
            # parse posted start/end into date objects (accept ISO and common localized formats)
            def _parse_date(s):
                from datetime import datetime
                if not s:
                    return None
                # Try ISO first
                for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%b. %d, %Y', '%b %d, %Y', '%B %d, %Y'):
                    try:
                        return datetime.strptime(s, fmt).date()
                    except Exception:
                        continue
                # Fallback: try to split and reconstruct if possible (e.g. 'Feb. 1, 2026')
                try:
                    return datetime.strptime(s.replace('.', ''), '%b %d, %Y').date()
                except Exception:
                    pass
                raise ValueError(f'Unrecognized date format: {s}')

            gstart_date = _parse_date(gstart) if gstart else start_date
            gend_date = _parse_date(gend) if gend else end_date

            ground = Ground.objects.get(id=ground_id)
            bookings_count = Booking.objects.filter(status='BOOKED', slot__ground=ground, slot__date__gte=gstart_date, slot__date__lte=gend_date).count()
            charge_val = float(charge)
            total = bookings_count * charge_val

            inv = GroundInvoice.objects.create(
                ground=ground,
                period_start=gstart_date,
                period_end=gend_date,
                bookings_count=bookings_count,
                charge_per_booking=charge_val,
                total_amount=total,
                is_paid=False
            )
            messages.success(request, f'Invoice created for {ground.name}: {bookings_count} bookings, total {total}')
            return redirect('admin_invoices')
        except Ground.DoesNotExist:
            messages.error(request, 'Invalid ground selected.')

    # Fetch existing invoices for display (last 50)
    existing_invoices = GroundInvoice.objects.all()[:50]

    rows = []
    for g in grounds:
        rows.append({
            'ground': g,
            'bookings_count': ground_counts.get(g.id, 0)
        })

    return render(request, 'dashboard/admin_invoices.html', {
        'rows': rows,
        'start_date': start_date,
        'end_date': end_date,
        'existing_invoices': existing_invoices,
        'selected_ground': selected_ground,
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
        now_dt = timezone.localtime(timezone.now())

        try:
            with transaction.atomic():
                slot = Slot.objects.select_for_update().get(id=slot_id, ground__owner=owner)

                if slot.is_booked or Booking.objects.filter(slot=slot, status='BOOKED').exists():
                    messages.error(request, 'Slot was booked just now. Please pick another slot.')
                    return redirect('/dashboard/owner/')

                if _slot_start_datetime(slot) <= now_dt:
                    messages.error(request, 'Past slots cannot be manually booked.')
                    return redirect('/owner/manual-booking/')

                if _is_restricted_manual_hour(slot.start_time):
                    messages.error(request, 'Manual booking is not allowed between 2:00 AM and 6:00 AM.')
                    return redirect('/owner/manual-booking/')

                # Calculate amount
                total_amount = _slot_price(slot.ground, slot.start_time)
                owner_payout = total_amount - 3

                booking = Booking.objects.create(
                    slot=slot,
                    customer_name=name,
                    customer_phone=phone,
                    total_amount=total_amount,
                    owner_payout=owner_payout,
                    booking_source='MANUAL',
                    payment_mode='FULL',
                    payment_status='PENDING',
                    paid_amount=0,
                    due_amount=total_amount,
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

    now_dt = timezone.localtime(timezone.now())

    if selected_ground and selected_date:
        slots_qs = Slot.objects.filter(ground=selected_ground, date=selected_date, is_booked=False).order_by('start_time')
        for s in slots_qs:
            if _slot_start_datetime(s) <= now_dt:
                continue
            if _is_restricted_manual_hour(s.start_time):
                continue
            price = _slot_price(s.ground, s.start_time)
            slots.append({'slot': s, 'price': price})
    else:
        # default: show all available upcoming slots across grounds owned by this owner
        slots_qs = Slot.objects.filter(ground__in=grounds, is_booked=False, date__gte=timezone.localdate()).order_by('date', 'start_time')
        for s in slots_qs:
            if _slot_start_datetime(s) <= now_dt:
                continue
            if _is_restricted_manual_hour(s.start_time):
                continue
            price = _slot_price(s.ground, s.start_time)
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
