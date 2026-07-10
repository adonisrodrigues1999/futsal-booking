from django.core.management.base import BaseCommand

from bookings.demo_data import purge_demo_data


class Command(BaseCommand):
    help = 'Delete demo data without reseeding it.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='Required flag to execute deletion.')

    def handle(self, *args, **options):
        if not options.get('confirm'):
            self.stdout.write(self.style.WARNING('Dry run only.'))
            self.stdout.write('This will delete demo users, grounds, bookings, tournaments, reviews, and related demo rows.')
            self.stdout.write('Re-run with: python manage.py purge_demo_data --confirm')
            return

        purge_demo_data()
        self.stdout.write(self.style.SUCCESS('Demo data deleted successfully.'))
