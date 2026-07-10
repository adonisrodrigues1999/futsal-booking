from datetime import datetime, timedelta, time
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from bookings.demo_data import purge_demo_data
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
  <text x="600" y="430" text-anchor="middle" font-family="Arial, sans-serif" font-size="28" fill="rgba(255,255,255,0.82)">FootBook Goa Event</text>
</svg>"""
    return ContentFile(svg.encode('utf-8'))


class Command(BaseCommand):
    help = 'Create a full demo environment with dummy data for FootBook.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Remove previously created demo data first.')
        parser.add_argument('--force', action='store_true', help='Allow seeding even if demo mode is not enabled.')

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

    def _upsert_ground(self, *, name, owner, location, day_price, night_price):
        ground, _ = Ground.objects.get_or_create(
            name=name,
            defaults={
                'location': location,
                'owner': owner,
                'day_price': day_price,
                'night_price': night_price,
                'opening_time': time(6, 0),
                'closing_time': time(23, 0),
                'image': DEMO_GROUND_IMAGE,
                'is_active': True,
            },
        )
        ground.location = location
        ground.owner = owner
        ground.day_price = day_price
        ground.night_price = night_price
        ground.opening_time = time(6, 0)
        ground.closing_time = time(23, 0)
        ground.image = DEMO_GROUND_IMAGE
        ground.is_active = True
        ground.save()
        return ground

    def _seed_slots_and_bookings(self, ground, booking_specs):
        required_dates = sorted({slot_date for slot_date, *_ in booking_specs})
        for slot_date in required_dates:
            ensure_slots_for_ground_date(ground, slot_date)
            ensure_slots_for_ground_date(ground, slot_date + timedelta(days=1))

        bookings = []
        for slot_date, start_time, booking_source, payment_mode, paid_amount, due_amount, customer_obj, customer_name, customer_phone in booking_specs:
            slot = Slot.objects.filter(ground=ground, date=slot_date, start_time=start_time).first()
            if not slot:
                continue

            total_amount = ground.day_price if start_time.hour < 18 else ground.night_price
            booking, created = Booking.objects.get_or_create(
                slot=slot,
                defaults={
                    'user': customer_obj,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'duration_hours': 1,
                    'total_amount': total_amount,
                    'platform_fee': 0,
                    'owner_payout': total_amount,
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
        if not options['force'] and not getattr(settings, 'FOOTBOOK_DEMO_MODE', False):
            raise CommandError(
                'Demo seeding is disabled unless FOOTBOOK_DEMO_MODE=true is set for this environment.'
            )

        if options['reset']:
            self.stdout.write('Clearing prior demo data...')
            purge_demo_data()

        admin = self._get_or_create_user(
            email='demo_admin@example.com',
            phone_number='9000000001',
            name='Goa Admin',
            role='admin',
            password='demo12345',
            is_staff=True,
        )
        owner = self._get_or_create_user(
            email='demo_owner@example.com',
            phone_number='9000000002',
            name='Goa Turf Owner',
            role='owner',
            password='demo12345',
        )
        assistant_owner = self._get_or_create_user(
            email='demo_owner2@example.com',
            phone_number='9000000003',
            name='Goa Beachside Owner',
            role='owner',
            password='demo12345',
        )
        referrer = self._get_or_create_user(
            email='demo_referrer@example.com',
            phone_number='9000000004',
            name='Goa Referrer',
            role='customer',
            password='demo12345',
        )
        customer = self._get_or_create_user(
            email='demo_customer@example.com',
            phone_number='9000000005',
            name='Goa Captain',
            role='customer',
            password='demo12345',
        )
        customer.referred_by = referrer
        customer.booking_count = 28
        customer.loyalty_points = 140
        customer.free_booking_credits = 2
        customer.save(update_fields=['referred_by', 'booking_count', 'loyalty_points', 'free_booking_credits'])

        backup_customer = self._get_or_create_user(
            email='demo_player@example.com',
            phone_number='9000000006',
            name='Goa Player',
            role='customer',
            password='demo12345',
        )

        extra_customer = self._get_or_create_user(
            email='demo_guest@example.com',
            phone_number='9000000007',
            name='Goa Guest',
            role='customer',
            password='demo12345',
        )

        support_owner = self._get_or_create_user(
            email='demo_owner3@example.com',
            phone_number='9000000008',
            name='Goa League Owner',
            role='owner',
            password='demo12345',
        )

        today = timezone.localdate()
        month_start = today.replace(day=1)
        past_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        primary_ground = self._upsert_ground(
            name='Goa Turf Arena',
            owner=owner,
            location='Panaji, Goa',
            day_price=1000,
            night_price=1500,
        )
        partner_ground = self._upsert_ground(
            name='Goa Beach Arena',
            owner=assistant_owner,
            location='Calangute, Goa',
            day_price=1200,
            night_price=1500,
        )
        league_ground = self._upsert_ground(
            name='Goa League Hub',
            owner=support_owner,
            location='Margao, Goa',
            day_price=500,
            night_price=1000,
        )

        self._seed_slots_and_bookings(primary_ground, [
            (past_days[0], time(7, 0), 'ONLINE', 'FULL', 1000, 0, customer, customer.name, customer.phone_number),
            (past_days[1], time(19, 0), 'ONLINE', 'PARTIAL_99', 99, 1401, customer, customer.name, customer.phone_number),
            (past_days[2], time(8, 0), 'MANUAL', 'FULL', 1000, 0, backup_customer, 'Goa Tuesday Crew', '9000000101'),
        ])
        self._seed_slots_and_bookings(partner_ground, [
            (past_days[3], time(9, 0), 'ONLINE', 'FULL', 1200, 0, extra_customer, extra_customer.name, extra_customer.phone_number),
            (past_days[4], time(20, 0), 'ONLINE', 'PARTIAL_99', 99, 1401, referrer, referrer.name, referrer.phone_number),
            (past_days[5], time(10, 0), 'MANUAL', 'FULL', 1200, 0, customer, 'Goa Weekend Team', '9000000102'),
        ])
        self._seed_slots_and_bookings(league_ground, [
            (past_days[6], time(7, 0), 'ONLINE', 'FULL', 500, 0, backup_customer, backup_customer.name, backup_customer.phone_number),
            (past_days[1], time(19, 0), 'ONLINE', 'FULL', 1000, 0, extra_customer, extra_customer.name, extra_customer.phone_number),
            (past_days[0], time(8, 0), 'MANUAL', 'FULL', 500, 0, customer, 'Goa Early Kickoff Crew', '9000000103'),
        ])

        month_history_specs = []
        month_dates = [month_start + timedelta(days=offset) for offset in range(min(4, max((today - month_start).days + 1, 0)))]
        if month_dates:
            first_month_day = month_dates[0]
            month_history_specs.append((first_month_day, time(7, 0), 'ONLINE', 'FULL', 1000, 0, customer, 'Goa Month Opener', '9000000104'))
        if len(month_dates) > 1:
            month_history_specs.append((month_dates[1], time(19, 0), 'ONLINE', 'PARTIAL_99', 99, 1401, extra_customer, 'Goa Mid-Month Rush', '9000000105'))
        if len(month_dates) > 2:
            month_history_specs.append((month_dates[2], time(8, 0), 'MANUAL', 'FULL', 500, 0, backup_customer, 'Goa Monthly Meetup', '9000000106'))
        if len(month_dates) > 3:
            month_history_specs.append((month_dates[3], time(20, 0), 'MANUAL', 'FULL', 1500, 0, customer, 'Goa Under Lights', '9000000107'))
        if month_history_specs:
            self._seed_slots_and_bookings(league_ground, month_history_specs)

        self._seed_slots_and_bookings(primary_ground, [
            (today + timedelta(days=1), time(7, 0), 'ONLINE', 'FULL', 1000, 0, customer, customer.name, customer.phone_number),
            (today + timedelta(days=1), time(19, 0), 'ONLINE', 'PARTIAL_99', 99, 1401, customer, customer.name, customer.phone_number),
            (today + timedelta(days=2), time(8, 0), 'MANUAL', 'FULL', 1000, 0, backup_customer, 'Goa Wednesday Crew', '9000000101'),
        ])
        self._seed_slots_and_bookings(partner_ground, [
            (today + timedelta(days=1), time(9, 0), 'ONLINE', 'FULL', 1200, 0, extra_customer, extra_customer.name, extra_customer.phone_number),
            (today + timedelta(days=1), time(20, 0), 'ONLINE', 'PARTIAL_99', 99, 1401, referrer, referrer.name, referrer.phone_number),
            (today + timedelta(days=3), time(10, 0), 'MANUAL', 'FULL', 1200, 0, customer, 'Goa Sunday Team', '9000000102'),
        ])
        self._seed_slots_and_bookings(league_ground, [
            (today + timedelta(days=1), time(7, 0), 'ONLINE', 'FULL', 500, 0, backup_customer, backup_customer.name, backup_customer.phone_number),
            (today + timedelta(days=1), time(19, 0), 'ONLINE', 'FULL', 1000, 0, extra_customer, extra_customer.name, extra_customer.phone_number),
            (today + timedelta(days=2), time(8, 0), 'MANUAL', 'FULL', 500, 0, customer, 'Goa Early Kickoff Crew', '9000000103'),
        ])

        OwnerExpense.objects.get_or_create(
            owner=owner,
            ground=primary_ground,
            title='Goa Turf Lighting Repair',
            defaults={
                'category': 'MAINTENANCE',
                'amount': 2500,
                'spent_on': today - timedelta(days=2),
                'note': 'Used for Goa showcase expense reporting.',
            },
        )
        OwnerExpense.objects.get_or_create(
            owner=assistant_owner,
            ground=partner_ground,
            title='Goa Beach Turf Deep Clean',
            defaults={
                'category': 'MAINTENANCE',
                'amount': 3500,
                'spent_on': today - timedelta(days=1),
                'note': 'Fresh cleanup before weekend bookings.',
            },
        )
        OwnerExpense.objects.get_or_create(
            owner=support_owner,
            ground=league_ground,
            title='Goa League Scoreboard Upgrade',
            defaults={
                'category': 'EQUIPMENT',
                'amount': 1500,
                'spent_on': today - timedelta(days=3),
                'note': 'Added before the showcase night.',
            },
        )

        tournament, _ = Tournament.objects.get_or_create(
            ground=primary_ground,
            title='Goa Weekend Cup',
            defaults={
                'description': 'Fast-paced 7-a-side futsal tournament for the Goa walkthrough.',
                'start_date': today + timedelta(days=10),
                'end_date': today + timedelta(days=11),
                'start_time': time(9, 0),
                'registration_deadline': today + timedelta(days=7),
                'entry_fee': 500,
                'prize_details': 'Winner trophy + branded kit',
                'max_teams': 16,
                'contact_name': 'Aarav Fernandes',
                'contact_phone': '9000011111',
                'category_fees': [
                    {'name': 'Open Men', 'fee': 500},
                    {'name': 'Women Open', 'fee': 500},
                ],
                'rules': 'Knockout format. 10-minute halves.',
                'status': 'UPCOMING',
                'is_published': True,
            },
        )
        tournament.description = 'Fast-paced 7-a-side futsal tournament for the Goa walkthrough.'
        tournament.start_date = today + timedelta(days=10)
        tournament.end_date = today + timedelta(days=11)
        tournament.start_time = time(9, 0)
        tournament.registration_deadline = today + timedelta(days=7)
        tournament.entry_fee = 500
        tournament.prize_details = 'Winner trophy + branded kit'
        tournament.max_teams = 16
        tournament.contact_name = 'Aarav Fernandes'
        tournament.contact_phone = '9000011111'
        tournament.category_fees = [
            {'name': 'Open Men', 'fee': 500},
            {'name': 'Women Open', 'fee': 500},
        ]
        tournament.rules = 'Knockout format. 10-minute halves.'
        tournament.status = 'UPCOMING'
        tournament.is_published = True
        tournament.save()

        tournament_two, _ = Tournament.objects.get_or_create(
            ground=partner_ground,
            title='Goa City Night League',
            defaults={
                'description': 'A local 5-a-side league with strong weekday signups in Goa.',
                'start_date': today + timedelta(days=14),
                'end_date': today + timedelta(days=15),
                'start_time': time(20, 0),
                'registration_deadline': today + timedelta(days=11),
                'entry_fee': 1000,
                'prize_details': 'Trophy, medals, and sponsored kits',
                'max_teams': 12,
                'contact_name': 'Nikhil Fernandes',
                'contact_phone': '9000012222',
                'category_fees': [
                    {'name': 'Corporate', 'fee': 1000},
                    {'name': 'Open', 'fee': 1000},
                ],
                'rules': 'League format. 12-minute halves.',
                'status': 'UPCOMING',
                'is_published': True,
            },
        )
        tournament_two.description = 'A local 5-a-side league with strong weekday signups in Goa.'
        tournament_two.start_date = today + timedelta(days=14)
        tournament_two.end_date = today + timedelta(days=15)
        tournament_two.start_time = time(20, 0)
        tournament_two.registration_deadline = today + timedelta(days=11)
        tournament_two.entry_fee = 1000
        tournament_two.prize_details = 'Trophy, medals, and sponsored kits'
        tournament_two.max_teams = 12
        tournament_two.contact_name = 'Nikhil Fernandes'
        tournament_two.contact_phone = '9000012222'
        tournament_two.category_fees = [
            {'name': 'Corporate', 'fee': 1000},
            {'name': 'Open', 'fee': 1000},
        ]
        tournament_two.rules = 'League format. 12-minute halves.'
        tournament_two.status = 'UPCOMING'
        tournament_two.is_published = True
        tournament_two.save()

        tournament_three, _ = Tournament.objects.get_or_create(
            ground=league_ground,
            title='Goa League Challenge',
            defaults={
                'description': 'Weekend challenge series for teams who want more match time in Goa.',
                'start_date': today + timedelta(days=18),
                'end_date': today + timedelta(days=19),
                'start_time': time(9, 0),
                'registration_deadline': today + timedelta(days=15),
                'entry_fee': 500,
                'prize_details': 'Winning jersey set and a trophy',
                'max_teams': 16,
                'contact_name': 'Imran Shaikh',
                'contact_phone': '9000013333',
                'category_fees': [
                    {'name': 'Open', 'fee': 500},
                    {'name': 'Corporate', 'fee': 500},
                ],
                'rules': 'Short matches. Fast turnaround.',
                'status': 'UPCOMING',
                'is_published': True,
            },
        )
        tournament_three.description = 'Weekend challenge series for teams who want more match time in Goa.'
        tournament_three.start_date = today + timedelta(days=18)
        tournament_three.end_date = today + timedelta(days=19)
        tournament_three.start_time = time(9, 0)
        tournament_three.registration_deadline = today + timedelta(days=15)
        tournament_three.entry_fee = 500
        tournament_three.prize_details = 'Winning jersey set and a trophy'
        tournament_three.max_teams = 16
        tournament_three.contact_name = 'Imran Shaikh'
        tournament_three.contact_phone = '9000013333'
        tournament_three.category_fees = [
            {'name': 'Open', 'fee': 500},
            {'name': 'Corporate', 'fee': 500},
        ]
        tournament_three.rules = 'Short matches. Fast turnaround.'
        tournament_three.status = 'UPCOMING'
        tournament_three.is_published = True
        tournament_three.save()

        reg, created = TournamentRegistration.objects.get_or_create(
            tournament=tournament,
            team_name='Goa Strikers',
            defaults={
                'user': customer,
                'captain_name': customer.name,
                'contact_phone': customer.phone_number,
                'contact_email': customer.email,
                'category_name': 'Open Men',
                'fee_amount': 500,
                'status': 'REGISTERED',
                'notes': 'Goa registration for pitch-day walkthrough.',
            },
        )
        reg.user = customer
        reg.captain_name = customer.name
        reg.contact_phone = customer.phone_number
        reg.contact_email = customer.email
        reg.category_name = 'Open Men'
        reg.fee_amount = 500
        reg.status = 'REGISTERED'
        reg.notes = 'Goa registration for pitch-day walkthrough.'
        reg.save()
        if created:
            award_tournament_registration_rewards(reg)

        reg_two, created_two = TournamentRegistration.objects.get_or_create(
            tournament=tournament_two,
            team_name='Goa United',
            defaults={
                'user': extra_customer,
                'captain_name': extra_customer.name,
                'contact_phone': extra_customer.phone_number,
                'contact_email': extra_customer.email,
                'category_name': 'Corporate',
                'fee_amount': 1000,
                'status': 'REGISTERED',
                'notes': 'Weeknight league registration for Goa exploration.',
            },
        )
        reg_two.user = extra_customer
        reg_two.captain_name = extra_customer.name
        reg_two.contact_phone = extra_customer.phone_number
        reg_two.contact_email = extra_customer.email
        reg_two.category_name = 'Corporate'
        reg_two.fee_amount = 1000
        reg_two.status = 'REGISTERED'
        reg_two.notes = 'Weeknight league registration for Goa exploration.'
        reg_two.save()
        if created_two:
            award_tournament_registration_rewards(reg_two)

        reg_three, created_three = TournamentRegistration.objects.get_or_create(
            tournament=tournament_three,
            team_name='Goa Phoenix',
            defaults={
                'user': backup_customer,
                'captain_name': backup_customer.name,
                'contact_phone': backup_customer.phone_number,
                'contact_email': backup_customer.email,
                'category_name': 'Open',
                'fee_amount': 500,
                'status': 'REGISTERED',
                'notes': 'Weekend challenge registration for the Goa walkthrough.',
            },
        )
        reg_three.user = backup_customer
        reg_three.captain_name = backup_customer.name
        reg_three.contact_phone = backup_customer.phone_number
        reg_three.contact_email = backup_customer.email
        reg_three.category_name = 'Open'
        reg_three.fee_amount = 500
        reg_three.status = 'REGISTERED'
        reg_three.notes = 'Weekend challenge registration for the Goa walkthrough.'
        reg_three.save()
        if created_three:
            award_tournament_registration_rewards(reg_three)

        GroundReview.objects.get_or_create(
            ground=primary_ground,
            user=customer,
            headline='Goa Crowd Favorite',
            defaults={
                'rating': 5,
                'comment': 'Bright lights, clean turf, and quick booking flow. Excellent for Goa match days.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=partner_ground,
            user=backup_customer,
            headline='Goa Match Day',
            defaults={
                'rating': 4,
                'comment': 'Good location and easy access. Strong candidate for tournament traffic.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=league_ground,
            user=extra_customer,
            headline='Goa League Night',
            defaults={
                'rating': 5,
                'comment': 'Great floodlights, proper seating, and the parking is easy.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=primary_ground,
            user=backup_customer,
            headline='Goa Night Session',
            defaults={
                'rating': 4,
                'comment': 'Evening slot looked polished and felt busy in the right way.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=partner_ground,
            user=extra_customer,
            headline='Goa Weekend Vibe',
            defaults={
                'rating': 5,
                'comment': 'Tournament-ready ground with enough scale for team events.',
            },
        )
        GroundReview.objects.get_or_create(
            ground=league_ground,
            user=customer,
            headline='Goa Budget Friendly',
            defaults={
                'rating': 4,
                'comment': 'Great value pricing for repeat weekly games.',
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
        AlertSubscription.objects.get_or_create(
            user=extra_customer,
            ground=partner_ground,
            defaults={
                'notify_price_drops': True,
                'notify_last_minute': True,
                'notify_nearby_tournaments': True,
                'email_enabled': True,
                'push_enabled': False,
            },
        )

        self.stdout.write(self.style.SUCCESS('Goa data created successfully.'))
        self.stdout.write('')
        self.stdout.write('Goa accounts:')
        self.stdout.write('  Admin:    demo_admin@example.com / demo12345')
        self.stdout.write('  Owner:    demo_owner@example.com / demo12345')
        self.stdout.write('  Owner 2:  demo_owner2@example.com / demo12345')
        self.stdout.write('  Owner 3:  demo_owner3@example.com / demo12345')
        self.stdout.write('  Customer: demo_customer@example.com / demo12345')
        self.stdout.write('  Player:   demo_player@example.com / demo12345')
        self.stdout.write('  Guest:    demo_guest@example.com / demo12345')
        self.stdout.write('')
        self.stdout.write('Primary demo story:')
        self.stdout.write(f'  Ground: {primary_ground.name}')
        self.stdout.write(f'  Tournament: {tournament.title}')
        self.stdout.write(f'  Customer points: {customer.loyalty_points}')
        self.stdout.write(f'  Customer free credits: {customer.free_booking_credits}')
