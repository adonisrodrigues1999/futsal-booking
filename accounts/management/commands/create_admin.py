from django.core.management.base import BaseCommand
from accounts.models import User

class Command(BaseCommand):
    help = 'Create admin user'

    def handle(self, *args, **options):
        if User.objects.filter(role='admin').exists():
            self.stdout.write(self.style.WARNING('Admin user already exists'))
            return

        admin = User.objects.create_superuser(
            email='admin@FootBook.com',
            phone_number='1234567890',
            name='System Admin',
            password='admin123',
            role='admin'
        )

        self.stdout.write(self.style.SUCCESS('Admin user created successfully!'))
        self.stdout.write('Email: admin@FootBook.com')
        self.stdout.write('Password: admin123')