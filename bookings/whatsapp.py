"""Non-blocking WhatsApp Cloud API notifications for ground owners."""

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)
MAX_SAME_DAY_BOOKINGS_IN_MESSAGE = 8


def _normalise_phone(phone):
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) == 10:
        return f'91{digits}'
    return digits


def _send_template(*, recipient, template_name, language, parameters=None):
    """Send a Cloud API template without exposing credentials in logs."""
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    if not all((token, phone_number_id, template_name, recipient)):
        return False
    template = {'name': template_name, 'language': {'code': language}}
    if parameters:
        template['components'] = [{
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(value)} for value in parameters],
        }]
    payload = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'template',
        'template': template,
    }
    version = getattr(settings, 'WHATSAPP_GRAPH_API_VERSION', 'v25.0')
    request = Request(
        f'https://graph.facebook.com/{version}/{phone_number_id}/messages',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=8) as response:
            if not 200 <= response.status < 300:
                logger.error('WhatsApp API rejected template=%s status=%s', template_name, response.status)
                return False
    except HTTPError as exc:
        logger.error('WhatsApp API HTTP error template=%s status=%s', template_name, exc.code)
        return False
    except (URLError, TimeoutError, OSError):
        logger.exception('WhatsApp API request failed template=%s', template_name)
        return False
    return True


def send_test_template(recipient, *, template_name='hello_world', language='en_US'):
    """Use Meta's allow-listed test recipient flow without enabling booking sends."""
    return _send_template(
        recipient=_normalise_phone(recipient),
        template_name=template_name,
        language=language,
    )


def _other_bookings_for_day(booking):
    """Return a compact same-ground schedule for the owner notification."""
    other_bookings = list(
        booking.__class__.objects.filter(
            slot__ground_id=booking.slot.ground_id,
            slot__date=booking.slot.date,
            status='BOOKED',
        ).exclude(pk=booking.pk).select_related('slot').order_by('slot__start_time')
    )
    if not other_bookings:
        return 'No other confirmed bookings for this date.'

    displayed = other_bookings[:MAX_SAME_DAY_BOOKINGS_IN_MESSAGE]
    lines = [
        f'{item.slot.start_time.strftime("%I:%M %p")}–{item.slot.end_time.strftime("%I:%M %p")} — {item.customer_name} — {item.get_payment_status_display()}'
        for item in displayed
    ]
    remaining = len(other_bookings) - len(displayed)
    if remaining:
        lines.append(f'Plus {remaining} more confirmed booking(s).')
    return '\n'.join(lines)


def send_owner_booking_update(booking):
    """Send a pre-approved template; failures must never affect a booking."""
    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        return False
    owner = booking.slot.ground.owner
    if not getattr(owner, 'whatsapp_booking_updates_enabled', False):
        return False
    recipient = _normalise_phone(getattr(owner, 'phone_number', ''))
    if not recipient:
        logger.warning('WhatsApp booking update skipped: owner has no valid phone booking=%s', booking.id)
        return False
    return _send_template(
        recipient=recipient,
        template_name=getattr(settings, 'WHATSAPP_BOOKING_TEMPLATE_NAME', ''),
        language=getattr(settings, 'WHATSAPP_TEMPLATE_LANGUAGE', 'en'),
        parameters=[
            booking.slot.date.strftime('%d %b %Y'),
            booking.slot.ground.name,
            f'{booking.slot.start_time.strftime("%I:%M %p")} - {booking.slot.end_time.strftime("%I:%M %p")}',
            booking.customer_name,
            booking.customer_phone,
            booking.get_status_display(),
            booking.get_payment_status_display(),
            _other_bookings_for_day(booking),
        ],
    )
