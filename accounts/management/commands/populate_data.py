from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import User
from grounds.models import Ground
from bookings.models import Slot, Booking, ActivityLog, CommissionLedger
import random

class Command(BaseCommand):
    help = 'Populate database with sample data for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample users...')

        # Create admin user
        admin = User.objects.create_superuser(
            email='admin@example.com',
            phone='1234567890',
            first_name='Admin',
            last_name='User',
            password='admin123'
        )

        # Create ground owners
        owners = []
        for i in range(3):
            owner = User.objects.create_user(
                email=f'owner{i+1}@example.com',
                phone=f'98765432{i+1}',
                first_name=f'Owner{i+1}',
                last_name='Smith',
                password='owner123',
                role='owner'
            )
            owners.append(owner)

        # Create customers
        customers = []
        for i in range(5):
            customer = User.objects.create_user(
                email=f'customer{i+1}@example.com',
                phone=f'555000{i+1}',
                first_name=f'Customer{i+1}',
                last_name='Doe',
                password='customer123',
                role='customer'
            )
            customers.append(customer)

        self.stdout.write('Creating sample grounds...')

        # Create grounds
        grounds = []
        ground_names = ['Green Field Arena', 'City Sports Complex', 'Premier Football Ground', 'Elite Turf Stadium']
        locations = ['Downtown', 'North Side', 'East District', 'West End']

        for i, (name, location) in enumerate(zip(ground_names, locations)):
            ground = Ground.objects.create(
                name=name,
                location=location,
                description=f'A premium football ground located in {location}',
                owner=owners[i % len(owners)],
                price_per_hour=50.00 + (i * 10),
                is_available=True
            )
            grounds.append(ground)

        self.stdout.write('Creating sample slots...')

        # Create slots for each ground (9 AM to 9 PM, 1-hour slots)
        for ground in grounds:
            for hour in range(9, 21):  # 9 AM to 9 PM
                start = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
                end = timezone.now().replace(hour=hour+1, minute=0, second=0, microsecond=0)
                Slot.objects.get_or_create(
                    ground=ground,
                    date=start.date(),
                    start_time=start.time(),
                    defaults={
                        'end_time': end.time(),
                        'is_booked': False,
                    }
                )

        self.stdout.write('Creating sample bookings...')

        # Create some bookings
        slots = Slot.objects.all()
        for i in range(10):
            slot = random.choice(slots)
            customer = random.choice(customers)

            # Make sure slot is not booked
            if not slot.is_booked:
                # Determine price from ground's day/night price based on slot start time
                price_per_hour = slot.ground.day_price if (slot.start_time.hour >= 6 and slot.start_time.hour < 18) else slot.ground.night_price
                booking = Booking.objects.create(
                    slot=slot,
                    user=customer,
                    customer_name=customer.name if hasattr(customer, 'name') else customer.get_full_name(),
                    customer_phone=customer.phone_number if hasattr(customer, 'phone_number') else '',
                    duration_hours=1,
                    total_amount=price_per_hour,
                    platform_fee=int(price_per_hour * 0.03),
                    owner_payout=price_per_hour - int(price_per_hour * 0.03),
                    booking_source='ONLINE',
                    status='BOOKED'
                )

                # Mark slot as booked
                slot.is_booked = True
                slot.save()

                # Create activity log
                ActivityLog.objects.create(
                    booking=booking,
                    action='created',
                    details=f'Booking created by {customer.get_full_name()}'
                )

                # Create commission ledger entry
                CommissionLedger.objects.create(
                    booking=booking,
                    commission_amount=booking.total_price * 0.1,  # 10% commission
                    status='pending'
                )

        self.stdout.write(self.style.SUCCESS('Sample data created successfully!'))
        self.stdout.write('Admin login: admin@example.com / admin123')
        self.stdout.write('Owner login: owner1@example.com / owner123')
        self.stdout.write('Customer login: customer1@example.com / customer123')