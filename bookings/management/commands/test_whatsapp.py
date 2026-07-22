from django.core.management.base import BaseCommand, CommandError

from bookings.whatsapp import send_test_template


class Command(BaseCommand):
    help = 'Send Meta’s approved test template to an allow-listed WhatsApp test recipient.'

    def add_arguments(self, parser):
        parser.add_argument('recipient', help='Recipient number in international format, e.g. 919876543210')
        parser.add_argument('--template', default='hello_world')
        parser.add_argument('--language', default='en_US')

    def handle(self, *args, **options):
        if not send_test_template(
            options['recipient'],
            template_name=options['template'],
            language=options['language'],
        ):
            raise CommandError('WhatsApp test message was not accepted. Check the recipient allow-list, token, sender ID, and template.')
        self.stdout.write(self.style.SUCCESS('WhatsApp test template accepted by Meta.'))
