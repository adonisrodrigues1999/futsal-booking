"""Non-blocking WhatsApp Cloud API notifications for ground owners."""

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)


def _normalise_phone(phone):
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) == 10:
        return f'91{digits}'
    return digits


def send_owner_booking_update(booking):
    """Send a pre-approved template; failures must never affect a booking."""
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    template_name = getattr(settings, 'WHATSAPP_BOOKING_TEMPLATE_NAME', '')
    if not getattr(settings, 'WHATSAPP_ENABLED', False) or not all((token, phone_number_id, template_name)):
        return False

    owner = booking.slot.ground.owner
    recipient = _normalise_phone(getattr(owner, 'phone_number', ''))
    if not recipient:
        logger.warning('WhatsApp booking update skipped: owner has no valid phone booking=%s', booking.id)
        return False

    parameters = [
        booking.slot.date.strftime('%d %b %Y'),
        booking.slot.ground.name,
        f'{booking.slot.start_time.strftime("%I:%M %p")} - {booking.slot.end_time.strftime("%I:%M %p")}',
        booking.customer_name,
        booking.customer_phone,
        booking.get_status_display(),
        booking.get_payment_status_display(),
    ]
    payload = {
        'messaging_product': 'whatsapp',
        'to': recipient,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': getattr(settings, 'WHATSAPP_TEMPLATE_LANGUAGE', 'en')},
            'components': [{
                'type': 'body',
                'parameters': [{'type': 'text', 'text': str(value)} for value in parameters],
            }],
        },
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
                logger.error('WhatsApp API rejected booking=%s status=%s', booking.id, response.status)
                return False
    except HTTPError as exc:
        logger.error('WhatsApp API HTTP error booking=%s status=%s', booking.id, exc.code)
        return False
    except (URLError, TimeoutError, OSError):
        logger.exception('WhatsApp API request failed booking=%s', booking.id)
        return False
    return True
