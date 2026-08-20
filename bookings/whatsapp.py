"""Non-blocking WhatsApp Cloud API notifications for ground owners."""

import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)
MAX_SAME_DAY_BOOKINGS_IN_MESSAGE = 8
MAX_TEMPLATE_PARAMETER_LENGTH = 900


def _normalise_phone(phone):
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) == 10:
        return f'91{digits}'
    return digits


def _template_text(value):
    """Make dynamic template values safe for Meta's text parameter rules."""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return (text or '-').replace('\x00', '')[:MAX_TEMPLATE_PARAMETER_LENGTH]


def _send_template(*, recipient, template_name, language, parameters=None):
    """Send a Cloud API template without exposing credentials in logs."""
    token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
    phone_number_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    if not all((token, phone_number_id, template_name, recipient)):
        logger.warning(
            'WhatsApp send skipped: incomplete configuration template=%s recipient_ending=%s',
            template_name or '-', recipient[-4:] if recipient else '-',
        )
        return False
    template = {'name': template_name, 'language': {'code': language}}
    if parameters:
        safe_parameters = [_template_text(value) for value in parameters]
        template['components'] = [{
            'type': 'body',
            'parameters': [{'type': 'text', 'text': value} for value in safe_parameters],
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
            logger.info(
                'WhatsApp template accepted by Meta template=%s recipient_ending=%s',
                template_name, recipient[-4:],
            )
    except HTTPError as exc:
        try:
            error_payload = json.loads(exc.read().decode('utf-8'))
            error = error_payload.get('error', {})
            detail = 'code=%s subcode=%s message=%s' % (
                error.get('code', '-'), error.get('error_subcode', '-'), error.get('message', '-'),
            )
        except Exception:
            detail = 'Meta returned an unreadable error response.'
        logger.error(
            'WhatsApp API HTTP error template=%s status=%s parameters=%s lengths=%s %s',
            template_name, exc.code, len(parameters or []),
            [len(value) for value in (safe_parameters if parameters else [])], detail,
        )
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


def send_customer_login_otp(phone_number, otp):
    """Send a pre-approved authentication template to a customer."""
    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        logger.warning('WhatsApp OTP skipped: WhatsApp is globally disabled')
        return False
    return _send_template(
        recipient=_normalise_phone(phone_number),
        template_name=getattr(settings, 'WHATSAPP_OTP_TEMPLATE_NAME', ''),
        language=getattr(settings, 'WHATSAPP_OTP_TEMPLATE_LANGUAGE', 'en'),
        parameters=[otp],
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
    # Meta template parameters are more reliable as a single line than as a
    # newline-delimited schedule, especially when customer names are variable.
    return ' | '.join(lines)


def send_owner_booking_update(booking):
    """Send a pre-approved template; failures must never affect a booking."""
    if not getattr(settings, 'WHATSAPP_ENABLED', False):
        logger.info('WhatsApp booking update skipped: globally disabled booking=%s', booking.id)
        return False
    owner = booking.slot.ground.owner
    if not getattr(owner, 'whatsapp_booking_updates_enabled', False):
        logger.info('WhatsApp booking update skipped: owner disabled booking=%s owner=%s', booking.id, owner.id)
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
