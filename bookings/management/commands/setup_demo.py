from datetime import datetime, timedelta, time
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking, Slot, OwnerExpense, AlertSubscription
from bookings.rewards import award_booking_rewards, award_tournament_registration_rewards
from bookings.slot_generation import ensure_slots_for_ground_date
from grounds.models import Ground, Tournament, TournamentRegistration, GroundReview


DEMO_GROUND_IMAGE = '/static/images/ground_placeholder.svg'


def _svg_file(label, fill="#19c37d"):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
  <rect width="1200" height="800" fill="#0f1c16"/>
  <circle cx="220" cy="180" r="210" fill="{fill}" fill-opacity="0.22"/>
  <circle cx="980" cy="620" r="260" fill="#f6a800" fill-opacity="0.18"/>
  <rect x="120" y="110" width="960" height="580" rx="36" fill="#173326" stroke="rgba(255,255,255,0.16)" stroke-width="3"/>
  <text x="600" y="355" text-anchor="middle" font-family="Arial, sans-serif" font-size="78" font-weight="700" fill="#ffffff">{label}</text>
  <text x="600" y="430" text-anchor="middle" font-family="Arial, sans-serif" font-size="28" fill="rgba(255,255,255,0.82)">FootBook Demo Event</text>
</svg>"""
    return ContentFile(svg.encode('utf-8'))


class Command(BaseCommand):
    help = 'Create a full demo environment with dummy data for FootBook.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Remove previously created demo data first.')

    def _get_or_create_user(self, *, email, phone_number, name, role, password, is_staff=False):
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={
                'phone_number': phone_number,
                'name': name,
                'role': role,
                'email_verified': True,
                'is_staff': is_staff,
                'is_active': True,
            },
        )
        user.phone_number = phone_number
        user.name = name
        user.role = role
        user.email_verified = True
        user.is_staff = is_staff
        user.is_active = True
        user.set_password(password)
        user.save()
        return user

    def _seed_slots_and_bookings(self, ground, customer, start_date):
        ensure_slots_for_ground_date(ground, start_date)
        ensure_slots_for_ground_date(ground, start_date + timedelta(days=1))

        morning_slot = Slot.objects.filter(ground=ground, date=start_date, start_time=time(7, 0)).first()
        evening_slot = Slot.objects.filter(ground=ground, date=start_date, start_time=time(19, 0)).first()
        next_day_slot = Slot.objects.filter(ground=ground, date=start_date + timedelta(days=1), start_time=time(8, 0)).first()

        bookings = []
        for slot, booking_source, payment_mode, paid_amount, due_amount, customer_name, customer_phone in [
            (morning_slot, 'ONLINE', 'FULL', ground.day_price, 0, customer.name, customer.phone_number),
            (evening_slot, 'ONLINE', 'PARTIAL_99', 99, max(ground.night_price - 99, 0), customer.name, customer.phone_number),
            (next_day_slot, 'MANUAL', 'FULL', ground.day_price, 0, 'Walk-in Demo Team', '9000000000'),
        ]:
            if not slot:
                continue
            booking, created = Booking.objects.get_or_create(
                slot=slot,
                defaults={
                    'user': customer if customer_name == customer.name else None,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'duration_hours': 1,
                    'total_amount': ground.day_price if slot.start_time.hour < 18 else ground.night_price,
                    'platform_fee': 0,
                    'owner_payout': ground.day_price if slot.start_time.hour < 18 else ground.night_price,
                    'booking_source': booking_source,
                    'status': 'BOOKED',
                    'payment_mode': payment_mode,
                    'payment_status': 'PAID' if due_amount == 0 else 'PARTIALLY_PAID',
                    'paid_amount': paid_amount,
                    'due_amount': due_amount,
                    'payment_paid_at': timezone.now(),
                },
            )
            if created:
                slot.is_booked = True
                slot.save(update_fields=['is_booked'])
                bookings.append(booking)
                if booking.user:
                    award_booking_rewards(booking)
            else:
                bookings.append(booking)

        return bookings

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            self.stdout.write('Clearing prior demo data...')
            GroundReview.objects.filter(headline__startswith='Demo').delete()
            TournamentRegistration.objects.filter(team_name__startswith='Demo').delete()
            Tournament.objects.filter(title__startswith='Demo').delete()
            OwnerExpense.objects.filter(title__startswith='Demo').delete()
            Booking.objects.filter(customer_name__icontains='Demo').delete()
            Slot.objects.filter(ground__name__startswith='Demo').delete()
            Ground.objects.filter(name__startswith='Demo').delete()
            User.objects.filter(email__startswith='demo_').delete()

        admin = self._get_or_create_user(
            email='demo_admin@example.com',
            phone_number='9000000001',
            name='Demo Admin',
            role='admin',
            password='demo12345',
            is_staff=True,
        )
        owner = self._get_or_create_user(
            email='demo_owner@example.com',
            phone_number='9000000002',
            name='Demo Owner',
            role='owner',
            password='demo12345',
        )
        assistant_owner = self._get_or_create_user(
            email='demo_owner2@example.com',
            phone_number='9000000003',
            name='Demo Ground Partner',
            role='owner',
            password='demo12345',
        )
        referrer = self._get_or_create_user(
            email='demo_referrer@example.com',
            phone_number='9000000004',
            name='Demo Referrer',
            role='customer',
            password='demo12345',
        )
        customer = self._get_or_create_user(
            email='demo_customer@example.com',
            phone_number='9000000005',
            name='Demo Customer',
            role='customer',
            password='demo12345',
        )
        customer.referred_by = referrer
        customer.booking_count = 19
        customer.loyalty_points = 95
        customer.free_booking_credits = 1
        customer.save(update_fields=['referred_by', 'booking_count', 'loyalty_points', 'free_booking_credits'])

        backup_customer = self._get_or_create_user(
            email='demo_player@example.com',
            phone_number='9000000006',
            name='Demo Player',
            role='customer',
            password='demo12345',
        )

        today = timezone.localdate()
        primary_ground, _ = Ground.objects.get_or_create(
            name='Demo Turf Arena',
            defaults={
                'location': 'Koramangala, Bengaluru',
                'owner': owner,
                'day_price': 799,
                'night_price': 1099,
                'opening_time': time(6, 0),
                'closing_time': time(23, 0),
                'image': DEMO_GROUND_IMAGE,
                'is_active': True,
            },
        )
        primary_ground.location = 'Koramangala, Bengaluru'
        primary_ground.owner = owner
        primary_ground.day_price = 799
        primary_ground.night_price = 1099
        primary_ground.opening_time = time(6, 0)
        primary_ground.closing_time = time(23, 0)
        primary_ground.image = DEMO_GROUND_IMAGE
        primary_ground.is_active = True
        primary_ground.save()

        partner_ground, _ = Ground.objects.get_or_create(
            name='Demo City Arena',
            defaults={
                'location': 'Indiranagar, Bengaluru',
                'owner': assistant_owner,
                'day_price': 899,
                'night_price': 1199,
                'opening_time': time(6, 0),
                'closing_time': time(23, 0),
                'image': DEMO_GROUND_IMAGE,
                'is_active': True,
            },
        )
        partner_ground.location = 'Indiranagar, Bengaluru'
        partner_ground.owner = assistant_owner
        partner_ground.day_price = 899
        partner_ground.night_price = 1199
        partner_ground.opening_time = time(6, 0)
        partner_ground.closing_time = time(23, 0)
        partner_ground.image = DEMO_GROUND_IMAGE
        partner_ground.is_active = True
        partner_ground.save()

        demo_bookings = self._seed_slots_and_bookings(primary_ground, customer, today + timedelta(days=1))
        self._seed_slots_and_bookings(partner_ground, backup_customer, today + timedelta(days=2))

        OwnerExpense.objects.get_or_create(
            owner=owner,
            ground=primary_ground,
            title='Demo Turf Lighting Repair',
            defaults={
                'category': 'MAINTENANCE',
                'amount': 2500,
                'spent_on': today - timedelta(days=2),
                'note': 'Used for demo expense reporting.',
            },
        )

        tournament, _ = Tournament.objects.get_or_create(
            ground=primary_ground,
            title='Demo Weekend Cup',
            defaults={
                'description': 'Fast-paced 7-a-side futsal tournament for the demo walkthrough.',
                'start_date': today + timedelta(days=10),
                'end_date': today + timedelta(days=11),
                'start_time': time(9, 0),
                'registration_deadline': today + timedelta(days=7),
                'entry_fee': 500,
                'prize_details': 'Winner trophy + branded kit',
                'max_teams': 16,
                'contact_name': 'Aarav Sharma',
                'contact_phone': '9000011111',
                'category_fees': [
                    {'name': 'Open Men', 'fee': 500},
                    {'name': 'Women Open', 'fee': 300},
                ],
                'rules': 'Knockout format. 10-minute halves.',
                'status': 'UPCOMING',
                'is_published': True,
            },
        )
        tournament.description = 'Fast-paced 7-a-side futsal tournament for the demo walkthrough.'
        tournament.start_date = today + timedelta(days=10)
        tournament.end_date = today + timedelta(days=11)
        tournament.start_time = time(9, 0)
        tournament.registration_deadline = today + timedelta(days=7)
        tournament.entry_fee = 500
        tournament.prize_details = 'Winner trophy + branded kit'
        tournament.max_teams = 16
        tournament.contact_name = 'Aarav Sharma'
        tournament.contact_phone = '9000011111'
        tournament.category_fees = [
            {'name': 'Open Men', 'fee': 500},
            {'name': 'Women Open', 'fee': 300},
        ]
        tournament.rules = 'Knockout format. 10-minute halves.'
        tournament.status = 'UPCOMING'
        tournament.is_published = True
        tournament.save()

        reg, created = TournamentRegistration.objects.get_or_create(
            tournament=tournament,
            team_name='Demo Strikers',
            defaults={
                'user': customer,
                'captain_name': customer.name,
                'contact_phone': customer.phone_number,
                'contact_email': customer.email,
                'category_name': 'Open Men',
                'fee_amount': 500,
                'status': 'REGISTERED',
                'notes': 'Demo registration for pitch-day walkthrough.',
            },
        )
        reg.user = customer
        reg.captain_name = customer.name
        reg.contact_phone = customer.phone_number
        reg.contact_email = customer.email
        reg.category_name = 'Open Men'
        reg.fee_amount = 500
        reg.status = 'REGISTERED'
        reg.notes = 'Demo registration for pitch-day walkthrough.'
        reg.save()
        if created:
            award_tournament_registration_rewards(reg)

        GroundReview.objects.get_or_create(
            ground=primary_ground,
            user=customer,
            headline='Demo Crowd Favorite',
            defaults={
                'rating': 5,
                'comment': 'Bright lights, clean turf, and quick booking flow. Excellent for demo.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=partner_ground,
            user=backup_customer,
            headline='Demo Match Day',
            defaults={
                'rating': 4,
                'comment': 'Good location and easy access. Strong candidate for tournament traffic.',
            },
        )

        AlertSubscription.objects.get_or_create(
            user=customer,
            ground=primary_ground,
            defaults={
                'notify_price_drops': True,
                'notify_last_minute': True,
                'notify_nearby_tournaments': True,
                'email_enabled': True,
                'push_enabled': False,
            },
        )

        self.stdout.write(self.style.SUCCESS('Demo data created successfully.'))
        self.stdout.write('')
        self.stdout.write('Demo accounts:')
        self.stdout.write('  Admin:    demo_admin@example.com / demo12345')
        self.stdout.write('  Owner:    demo_owner@example.com / demo12345')
        self.stdout.write('  Customer: demo_customer@example.com / demo12345')
        self.stdout.write('  Player:   demo_player@example.com / demo12345')
        self.stdout.write('')
        self.stdout.write('Primary demo story:')
        self.stdout.write(f'  Ground: {primary_ground.name}')
        self.stdout.write(f'  Tournament: {tournament.title}')
        self.stdout.write(f'  Customer points: {customer.loyalty_points}')
        self.stdout.write(f'  Customer free credits: {customer.free_booking_credits}')
