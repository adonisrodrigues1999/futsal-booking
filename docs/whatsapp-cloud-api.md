# WhatsApp Cloud API setup

FootBook sends a template message only to the ground owner. The body template must have these seven variables, in this exact order:

1. Booking date
2. Ground name
3. Slot time range
4. Customer name
5. Customer phone number
6. Booking status
7. Payment status

Create an approved **Utility** template in Meta WhatsApp Manager, for example `ground_booking_update`, with a body similar to:

```text
Booking update
Date: {{1}}
Ground: {{2}}
Slot: {{3}}
Customer: {{4}} ({{5}})
Booking: {{6}}
Payment: {{7}}
```

## Meta configuration

1. In [Meta for Developers](https://developers.facebook.com/), create a Business app and add **WhatsApp**.
2. In WhatsApp > API Setup, add/verify the business phone number. Copy its **Phone number ID**.
3. Create a system user in Business Settings and generate a long-lived access token with WhatsApp messaging permissions. Do not use the temporary test token in production.
4. Add the approved template above and wait for approval.
5. Set these production environment variables (never commit them):

```env
WHATSAPP_ENABLED=true
WHATSAPP_GRAPH_API_VERSION=v25.0
WHATSAPP_ACCESS_TOKEN=your-system-user-token
WHATSAPP_PHONE_NUMBER_ID=your-meta-phone-number-id
WHATSAPP_BOOKING_TEMPLATE_NAME=ground_booking_update
WHATSAPP_TEMPLATE_LANGUAGE=en
WHATSAPP_WEBHOOK_VERIFY_TOKEN=a-long-random-secret
WHATSAPP_APP_SECRET=your-meta-app-secret
```

## Webhook

In WhatsApp > Configuration, set the callback URL to:

```text
https://your-domain.example/webhooks/whatsapp/
```

Set its verify token to `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, then subscribe to `messages`. FootBook validates Meta's GET verification and validates every POST against `X-Hub-Signature-256` using `WHATSAPP_APP_SECRET`. Delivery statuses are logged; they never change a booking.

See Meta's [Cloud API send-messages guide](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages/) and [webhook guide](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks/) for the current permission and dashboard steps.

## Test before enabling booking notifications

In Meta's API Setup screen, add and verify a recipient number under **To**. Then, while `WHATSAPP_ENABLED=false`, send the default Meta test template:

```bash
./venv/bin/python manage.py test_whatsapp 919876543210
```

Replace the number with the allow-listed recipient in international digits only. The command sends `hello_world` and does not send a booking notification. Once that works, create and approve `ground_booking_update`, add the App Secret and webhook configuration, enable WhatsApp globally, and turn it on for one owner in Admin Dashboard.

## Delivery behavior

The booking transaction completes first. Email and WhatsApp work is then submitted to a background executor; failures are logged and do not affect booking creation, payments, or email delivery. This is deliberately lightweight for the current deployment. For durable retries across worker restarts, move `_send_owner_booking_notifications` to Celery/RQ backed by Redis before treating WhatsApp delivery as guaranteed.
