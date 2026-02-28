from django.test import TestCase
from datetime import time, date
from datetime import timedelta

from accounts.models import User
from grounds.models import Ground
from django.utils import timezone

from .models import Slot, Booking, OwnerExpense
from .slot_generation import create_initial_slots_for_ground, ensure_slots_for_ground_date


class SlotGenerationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com',
            phone_number='9999999999',
            name='Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )

    def test_create_initial_slots_uses_opening_and_closing_times(self):
        ground = Ground.objects.create(
            name='Arena 1',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(9, 0),
        )

        create_initial_slots_for_ground(
            ground=ground,
            days=2,
            start_date=date(2026, 2, 19),
        )

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 6)

    def test_create_initial_slots_handles_cross_midnight_ranges(self):
        ground = Ground.objects.create(
            name='Arena 2',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(22, 0),
        )

        create_initial_slots_for_ground(
            ground=ground,
            days=1,
            start_date=date(2026, 2, 19),
            slot_config={
                'slot_1_start': time(18, 0),
                'slot_1_end': time(1, 0),
                'slot_2_start': None,
                'slot_2_end': None,
            },
        )

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 7)
        self.assertTrue(
            Slot.objects.filter(
                ground=ground,
                date=date(2026, 2, 20),
                start_time=time(0, 0),
            ).exists()
        )

    def test_ensure_slots_for_ground_date_is_idempotent(self):
        ground = Ground.objects.create(
            name='Arena 3',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(8, 0),
        )

        ensure_slots_for_ground_date(ground=ground, slot_date=date(2026, 2, 19))
        ensure_slots_for_ground_date(ground=ground, slot_date=date(2026, 2, 19))

        self.assertEqual(Slot.objects.filter(ground=ground).count(), 2)


class BookingFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='groundowner@example.com',
            phone_number='8888888888',
            name='Ground Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.customer = User.objects.create_user(
            email='customer@example.com',
            phone_number='7777777777',
            name='Customer',
            password='password123',
            role='customer',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='Arena Pro',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=900,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )

    def test_manual_booking_owner_payout_not_deducted(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=False,
        )
        self.client.force_login(self.owner)
        response = self.client.post('/owner/manual-booking/', {
            'slot': str(slot.id),
            'name': 'Walkin User',
            'phone': '9999911111',
        })
        self.assertEqual(response.status_code, 302)

        booking = Booking.objects.get(slot=slot, status='BOOKED')
        self.assertEqual(booking.total_amount, booking.owner_payout)

    def test_customer_reschedule_blocked_within_four_hours(self):
        near_start = timezone.localtime(timezone.now()) + timedelta(hours=2)
        slot = Slot.objects.create(
            ground=self.ground,
            date=near_start.date(),
            start_time=near_start.time().replace(second=0, microsecond=0),
            end_time=(near_start + timedelta(hours=1)).time().replace(second=0, microsecond=0),
            is_booked=True,
        )
        booking = Booking.objects.create(
            slot=slot,
            user=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone_number,
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )

        self.client.force_login(self.customer)
        response = self.client.get(f'/reschedule/{booking.id}/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/my-bookings/')

    def test_owner_mark_paid_at_ground_for_due_booking(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(20, 0),
            end_time=time(21, 0),
            is_booked=True,
        )
        booking = Booking.objects.create(
            slot=slot,
            customer_name='Manual Customer',
            customer_phone='6666611111',
            total_amount=900,
            owner_payout=900,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=900,
        )

        self.client.force_login(self.owner)
        response = self.client.post(f'/owner/mark-paid/{booking.id}/')
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'PAID')
        self.assertEqual(booking.due_amount, 0)
        self.assertEqual(booking.paid_amount, booking.total_amount)

    def test_owner_dashboard_shows_online_and_manual_money_split(self):
        online_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        manual_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=online_slot,
            user=self.customer,
            customer_name='Online Customer',
            customer_phone='7000000001',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )
        Booking.objects.create(
            slot=manual_slot,
            customer_name='Walk-in Customer',
            customer_phone='7000000002',
            total_amount=700,
            owner_payout=700,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=200,
            due_amount=500,
        )

        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/owner/')
        self.assertEqual(response.status_code, 200)

        stats = response.context['stats']
        self.assertEqual(stats['online_bookings'], 1)
        self.assertEqual(stats['manual_bookings'], 1)
        self.assertEqual(stats['online_paid_amount'], 500)
        self.assertEqual(stats['manual_paid_amount'], 200)
        self.assertEqual(stats['online_due_amount'], 0)
        self.assertEqual(stats['manual_due_amount'], 500)


class OwnerExpenseTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='expenseowner@example.com',
            phone_number='6666666666',
            name='Expense Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.other_owner = User.objects.create_user(
            email='otherowner@example.com',
            phone_number='5555555555',
            name='Other Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='Expense Ground',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=900,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )

    def test_owner_can_add_expense(self):
        self.client.force_login(self.owner)
        response = self.client.post('/dashboard/owner/expenses/add/', {
            'title': 'Monthly turf cleaning',
            'category': 'MAINTENANCE',
            'amount': '1200.50',
            'spent_on': timezone.localdate().strftime('%Y-%m-%d'),
            'ground_id': str(self.ground.id),
            'note': 'Deep clean and chemical wash',
            'next': '/dashboard/owner/'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(OwnerExpense.objects.filter(owner=self.owner, title='Monthly turf cleaning').exists())

    def test_owner_cannot_delete_other_owner_expense(self):
        expense = OwnerExpense.objects.create(
            owner=self.other_owner,
            title='Other owner cost',
            category='OTHER',
            amount='300.00',
            spent_on=timezone.localdate(),
        )
        self.client.force_login(self.owner)
        response = self.client.post(f'/dashboard/owner/expenses/{expense.id}/delete/', {'next': '/dashboard/owner/'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(OwnerExpense.objects.filter(id=expense.id).exists())
