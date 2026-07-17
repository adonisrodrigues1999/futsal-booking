import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from datetime import datetime, time, date
from datetime import timedelta
from unittest.mock import patch

from accounts.models import User
from grounds.models import Ground, Tournament, TournamentRegistration
from django.utils import timezone

from .models import Slot, Booking, OwnerExpense, BookingAttendance, GroundInvoice, InvoiceLineItem, OnlineSettlement, OnlineSettlementLineItem
from .slot_generation import create_initial_slots_for_ground, ensure_slots_for_ground_date
from .views import _slot_price_for_slot


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


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
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

    def test_manual_booking_can_repeat_every_two_weeks(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=False,
        )
        self.client.force_login(self.owner)
        response = self.client.post('/owner/manual-booking/', {
            'slot': str(slot.id),
            'name': 'Sunday Training',
            'phone': '9999911111',
            'repeat_enabled': 'on',
            'repeat_every_weeks': '2',
            'repeat_occurrences': '2',
        })
        self.assertEqual(response.status_code, 302)

        bookings = Booking.objects.filter(customer_name='Sunday Training', booking_source='MANUAL').order_by('slot__date')
        self.assertEqual(bookings.count(), 2)
        self.assertIsNotNone(bookings[0].recurrence_group)
        self.assertEqual(bookings[0].recurrence_group, bookings[1].recurrence_group)
        self.assertEqual(bookings[1].slot.date, slot.date + timedelta(days=14))

    def test_manual_booking_can_repeat_on_selected_weekdays(self):
        today = timezone.localdate()
        days_until_tuesday = (1 - today.weekday()) % 7 or 7
        base_date = today + timedelta(days=days_until_tuesday)
        slot = Slot.objects.create(
            ground=self.ground,
            date=base_date,
            start_time=time(17, 0),
            end_time=time(18, 0),
            is_booked=False,
        )
        self.client.force_login(self.owner)
        response = self.client.post('/owner/manual-booking/', {
            'slot': str(slot.id),
            'name': 'Weekly Training',
            'phone': '9999911111',
            'repeat_enabled': 'on',
            'repeat_every_weeks': '1',
            'repeat_occurrences': '2',
            'repeat_weekdays': ['1', '2', '5'],
        })
        self.assertEqual(response.status_code, 302)

        bookings = Booking.objects.filter(customer_name='Weekly Training', booking_source='MANUAL').order_by('slot__date', 'slot__start_time')
        self.assertEqual(bookings.count(), 6)
        self.assertIsNotNone(bookings[0].recurrence_group)
        self.assertEqual({b.recurrence_group for b in bookings}, {bookings[0].recurrence_group})
        self.assertEqual(bookings[0].slot.date, base_date)
        self.assertEqual(bookings[1].slot.date, base_date + timedelta(days=1))
        self.assertEqual(bookings[2].slot.date, base_date + timedelta(days=4))

    def test_owner_manual_booking_shows_day_and_night_badges(self):
        target_date = timezone.localdate() + timedelta(days=1)
        Slot.objects.create(
            ground=self.ground,
            date=target_date,
            start_time=time(8, 0),
            end_time=time(9, 0),
            is_booked=False,
        )
        Slot.objects.create(
            ground=self.ground,
            date=target_date,
            start_time=time(20, 0),
            end_time=time(21, 0),
            is_booked=False,
        )

        self.client.force_login(self.owner)
        response = self.client.get(
            f'/owner/manual-booking/?ground={self.ground.id}&date={target_date.isoformat()}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '☀️')
        self.assertContains(response, 'Day')
        self.assertContains(response, '🌙')
        self.assertContains(response, 'Night')

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
        self.assertEqual(booking.payment_status, 'PAID_AT_GROUND')
        self.assertEqual(booking.due_amount, 0)
        self.assertEqual(booking.paid_amount, booking.total_amount)

    def test_owner_cancel_booking_cancels_future_recurring_bookings(self):
        first_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=7),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        second_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=21),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        booking_one = Booking.objects.create(
            slot=first_slot,
            customer_name='Training Group',
            customer_phone='6666611111',
            total_amount=500,
            owner_payout=500,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=500,
            recurrence_group=uuid.uuid4(),
            recurrence_position=0,
        )
        booking_two = Booking.objects.create(
            slot=second_slot,
            customer_name='Training Group',
            customer_phone='6666611111',
            total_amount=500,
            owner_payout=500,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=500,
            recurrence_group=booking_one.recurrence_group,
            recurrence_position=1,
        )

        self.client.force_login(self.owner)
        response = self.client.get(f'/owner/cancel/{booking_one.id}/')
        self.assertEqual(response.status_code, 302)

        booking_one.refresh_from_db()
        booking_two.refresh_from_db()
        first_slot.refresh_from_db()
        second_slot.refresh_from_db()

        self.assertEqual(booking_one.status, 'CANCELLED')
        self.assertEqual(booking_two.status, 'CANCELLED')
        self.assertFalse(first_slot.is_booked)
        self.assertFalse(second_slot.is_booked)

    def test_ground_slot_status_endpoint_reflects_active_booking(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(15, 0),
            end_time=time(16, 0),
            is_booked=False,
        )
        Booking.objects.create(
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
            status='BOOKED',
        )
        self.client.force_login(self.customer)
        response = self.client.get(
            f'/grounds/{self.ground.id}/slot-status/?date={slot.date.isoformat()}&slot_ids={slot.id}'
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(len(payload.get('slots', [])), 1)
        self.assertTrue(payload['slots'][0]['is_booked'])

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

    def test_owner_dashboard_section_toggles_are_button_controls(self):
        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/owner/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-toggle-section="owner-extended-metrics"')
        self.assertContains(response, 'aria-controls="owner-extended-metrics"')
        self.assertContains(response, 'aria-controls="owner-grounds-performance"')
        self.assertContains(response, 'aria-controls="owner-tournaments-section"')

    def test_owner_dashboard_booking_rows_use_button_headers(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=slot,
            user=self.customer,
            customer_name='Accordion Customer',
            customer_phone='7000007777',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )

        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/owner/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="booking-accordion-header"')
        self.assertContains(response, 'aria-controls="booking-body-')

    def test_owner_dashboard_bookings_title_uses_weekday_abbreviation(self):
        target_date = timezone.localdate() + timedelta(days=3)
        slot = Slot.objects.create(
            ground=self.ground,
            date=target_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=slot,
            user=self.customer,
            customer_name='Title Customer',
            customer_phone='7000008888',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )

        self.client.force_login(self.owner)
        response = self.client.get(f'/dashboard/owner/?date={target_date.isoformat()}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target_date.strftime('%a, %b %d, %Y'))

    def test_manual_booking_page_prompts_for_review_before_submit(self):
        target_date = timezone.localdate() + timedelta(days=1)
        Slot.objects.create(
            ground=self.ground,
            date=target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False,
        )

        self.client.force_login(self.owner)
        response = self.client.get(
            f'/owner/manual-booking/?ground={self.ground.id}&date={target_date.isoformat()}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review & Book')
        self.assertContains(response, 'id="manualReviewModal"')
        self.assertContains(response, 'data-processing-overlay="true"')

    def test_partial_online_payment_monthly_split_and_ground_tally(self):
        today = timezone.localdate()
        partial_slot = Slot.objects.create(
            ground=self.ground,
            date=today,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_booked=True,
        )
        booking = Booking.objects.create(
            slot=partial_slot,
            user=self.customer,
            customer_name='Partial Customer',
            customer_phone='7000000099',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='PARTIAL_99',
            payment_status='PARTIALLY_PAID',
            paid_amount=99,
            due_amount=401,
        )

        self.client.force_login(self.owner)
        response = self.client.get('/dashboard/owner/')
        self.assertEqual(response.status_code, 200)
        stats = response.context['stats']
        self.assertEqual(stats['period_online_collection'], 99)
        self.assertEqual(stats['period_online_due_at_ground'], 401)
        self.assertEqual(stats['period_ground_collected'], 0)
        self.assertEqual(stats['period_ground_pending'], 401)
        self.assertEqual(stats['period_collected_at_ground_tally'], 0)

        mark_response = self.client.post(f'/owner/mark-paid/{booking.id}/')
        self.assertEqual(mark_response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.payment_status, 'PAID_AT_GROUND')
        self.assertEqual(booking.due_amount, 0)

        response_after = self.client.get('/dashboard/owner/')
        self.assertEqual(response_after.status_code, 200)
        stats_after = response_after.context['stats']
        self.assertEqual(stats_after['period_online_collection'], 99)
        self.assertEqual(stats_after['period_online_due_at_ground'], 0)
        self.assertEqual(stats_after['period_ground_collected'], 401)
        self.assertEqual(stats_after['period_ground_pending'], 0)
        self.assertEqual(stats_after['period_collected_at_ground_tally'], 401)

    def test_owner_can_mark_booking_attendance(self):
        started_at = timezone.localtime(timezone.now()) - timedelta(minutes=10)
        slot = Slot.objects.create(
            ground=self.ground,
            date=started_at.date(),
            start_time=started_at.time().replace(second=0, microsecond=0),
            end_time=(started_at + timedelta(hours=1)).time().replace(second=0, microsecond=0),
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

        self.client.force_login(self.owner)
        response = self.client.post(f'/owner/attendance/{booking.id}/', {'status': 'NO_SHOW'})
        self.assertEqual(response.status_code, 302)

        attendance = BookingAttendance.objects.get(booking=booking)
        self.assertEqual(attendance.status, 'NO_SHOW')
        self.assertEqual(attendance.marked_by, self.owner)

    def test_last_minute_dynamic_pricing_discount(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 17, 40), timezone.get_current_timezone())
        slot = Slot.objects.create(
            ground=self.ground,
            date=fixed_now.date(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            is_booked=False,
        )

        with patch('bookings.views.timezone.now', return_value=fixed_now):
            self.assertEqual(_slot_price_for_slot(slot), self.ground.night_price - 101)

    def test_last_minute_discount_uses_lower_amount_for_sub_700_bookings(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 17, 40), timezone.get_current_timezone())
        self.ground.night_price = 650
        self.ground.save(update_fields=['night_price'])
        slot = Slot.objects.create(
            ground=self.ground,
            date=fixed_now.date(),
            start_time=time(18, 0),
            end_time=time(19, 0),
            is_booked=False,
        )

        with patch('bookings.views.timezone.now', return_value=fixed_now):
            self.assertEqual(_slot_price_for_slot(slot), 599)

    def test_booked_slot_does_not_receive_dynamic_discount(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 9, 40), timezone.get_current_timezone())
        slot = Slot.objects.create(
            ground=self.ground,
            date=fixed_now.date(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True,
        )

        with patch('bookings.views.timezone.now', return_value=fixed_now):
            self.assertEqual(_slot_price_for_slot(slot), self.ground.day_price)

    def test_free_booking_credit_redeems_without_razorpay(self):
        self.customer.free_booking_credits = 1
        self.customer.save(update_fields=['free_booking_credits'])
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False,
        )

        self.client.force_login(self.customer)
        response = self.client.post(
            '/payments/razorpay/create-order/',
            data='{"slot_id": %s, "payment_mode": "FREE_REWARD"}' % slot.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['free_booking'])

        booking = Booking.objects.get(slot=slot, status='BOOKED')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.free_booking_credits, 0)
        self.assertEqual(self.customer.booking_count, 1)
        self.assertEqual(self.customer.loyalty_points, 5)
        self.assertTrue(booking.loyalty_reward_redeemed)
        self.assertEqual(booking.reward_discount_amount, booking.total_amount)

    def test_free_booking_credit_blocked_for_evening_slot(self):
        self.customer.free_booking_credits = 1
        self.customer.save(update_fields=['free_booking_credits'])
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(18, 0),
            end_time=time(19, 0),
            is_booked=False,
        )

        self.client.force_login(self.customer)
        response = self.client.post(
            '/payments/razorpay/create-order/',
            data='{"slot_id": %s, "payment_mode": "FREE_REWARD"}' % slot.id,
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('morning slots', response.json().get('error', '').lower())

    def test_manual_recurring_booking_conflict_requires_confirmation(self):
        first_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=7),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=False,
        )
        second_slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=21),
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=second_slot,
            customer_name='Existing Group',
            customer_phone='8888800000',
            total_amount=500,
            owner_payout=500,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=500,
        )

        self.client.force_login(self.owner)
        payload = {
            'ground': str(self.ground.id),
            'date': first_slot.date.strftime('%Y-%m-%d'),
            'slot': str(first_slot.id),
            'name': 'Training Group',
            'phone': '9999911111',
            'repeat_enabled': 'on',
            'repeat_every_weeks': '2',
            'repeat_occurrences': '2',
        }

        preview_response = self.client.post('/owner/manual-booking/', payload)
        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, 'Some recurring slots are already booked', html=False)
        self.assertFalse(Booking.objects.filter(customer_name='Training Group', booking_source='MANUAL').exists())

        confirm_payload = dict(payload)
        confirm_payload['confirm_conflicts'] = '1'
        confirm_response = self.client.post('/owner/manual-booking/', confirm_payload)
        self.assertEqual(confirm_response.status_code, 302)

        bookings = Booking.objects.filter(customer_name='Training Group', booking_source='MANUAL').order_by('slot__date')
        self.assertEqual(bookings.count(), 1)
        self.assertEqual(bookings.first().slot, first_slot)

    def test_discounted_free_slot_bypasses_razorpay(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 16, 30), timezone.get_current_timezone())
        slot = Slot.objects.create(
            ground=self.ground,
            date=fixed_now.date(),
            start_time=time(17, 0),
            end_time=time(18, 0),
            is_booked=False,
        )

        self.ground.day_price = 50
        self.ground.save(update_fields=['day_price'])

        self.client.force_login(self.customer)
        with patch('bookings.views.timezone.now', return_value=fixed_now):
            response = self.client.post(
                '/payments/razorpay/create-order/',
                data='{"slot_id": %s, "payment_mode": "FULL"}' % slot.id,
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['free_booking'])

        booking = Booking.objects.get(slot=slot, status='BOOKED')
        self.assertEqual(booking.total_amount, 0)
        self.assertEqual(booking.payment_status, 'PAID')

    def test_tournament_registration_awards_points(self):
        referrer = User.objects.create_user(
            email='referrer@example.com',
            phone_number='6666000000',
            name='Referrer',
            password='password123',
            role='customer',
            email_verified=True,
        )
        self.customer.referred_by = referrer
        self.customer.save(update_fields=['referred_by'])

        tournament = Tournament.objects.create(
            ground=self.ground,
            title='Weekend Cup',
            description='Fast-paced tournament',
            start_date=timezone.localdate() + timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=11),
            entry_fee=500,
            contact_phone='9999912345',
            category_fees=[{'name': 'Open', 'fee': 500}],
            is_published=True,
        )

        self.client.force_login(self.customer)
        response = self.client.post(f'/tournaments/{tournament.id}/register/', {
            'team_name': 'Storm FC',
            'captain_name': 'Captain',
            'contact_phone': '8888800000',
            'contact_email': 'team@example.com',
            'category_name': 'Open',
            'notes': 'See you there',
        })
        self.assertEqual(response.status_code, 302)

        registration = TournamentRegistration.objects.get(tournament=tournament, team_name='Storm FC')
        self.customer.refresh_from_db()
        referrer.refresh_from_db()
        self.assertEqual(registration.fee_amount, 500)
        self.assertEqual(self.customer.loyalty_points, 20)
        self.assertEqual(referrer.loyalty_points, 20)


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


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class AdminInvoiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com',
            phone_number='4444444444',
            name='Admin',
            password='password123',
            role='admin',
            email_verified=True,
        )
        self.owner = User.objects.create_user(
            email='invoiceowner@example.com',
            phone_number='4333333333',
            name='Invoice Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.ground_one = Ground.objects.create(
            name='Invoice Arena One',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=900,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )
        self.ground_two = Ground.objects.create(
            name='Invoice Arena Two',
            location='City',
            owner=self.owner,
            day_price=600,
            night_price=1000,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )
        self.settlement_date = timezone.localdate() + timedelta(days=1)
        self.slot_one = Slot.objects.create(
            ground=self.ground_one,
            date=self.settlement_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        self.slot_two = Slot.objects.create(
            ground=self.ground_two,
            date=self.settlement_date,
            start_time=time(11, 0),
            end_time=time(12, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=self.slot_one,
            customer_name='Ground One User',
            customer_phone='9000000001',
            total_amount=500,
            owner_payout=500,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=500,
        )
        Booking.objects.create(
            slot=self.slot_two,
            customer_name='Ground Two User',
            customer_phone='9000000002',
            total_amount=600,
            owner_payout=600,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=600,
        )

    def test_admin_creates_settlement_per_ground_with_line_items(self):
        self.client.force_login(self.admin)
        response = self.client.post('/dashboard/admin/invoices/', {
            'ground_id': str(self.ground_one.id),
            'charge_per_booking': '125.50',
            'period_start': self.settlement_date.strftime('%Y-%m-%d'),
            'period_end': self.settlement_date.strftime('%Y-%m-%d'),
        })
        self.assertEqual(response.status_code, 302)

        invoice = GroundInvoice.objects.get(ground=self.ground_one)
        self.assertEqual(invoice.bookings_count, 1)
        self.assertEqual(invoice.charge_per_booking, Decimal('125.50'))
        self.assertEqual(invoice.total_amount, Decimal('125.50'))
        self.assertFalse(invoice.is_paid)
        self.assertIsNone(invoice.settled_at)
        self.assertEqual(InvoiceLineItem.objects.filter(invoice=invoice).count(), 1)
        self.assertIsNotNone(Booking.objects.get(slot=self.slot_one).invoiced_at)
        self.assertFalse(GroundInvoice.objects.filter(ground=self.ground_two).exists())

        summary_response = self.client.get(
            f'/dashboard/admin/invoices/?start={self.settlement_date.strftime("%Y-%m-%d")}&end={self.settlement_date.strftime("%Y-%m-%d")}'
        )
        self.assertEqual(summary_response.status_code, 200)
        rows = {row['ground'].id: row['bookings_count'] for row in summary_response.context['rows']}
        self.assertEqual(rows[self.ground_one.id], 0)
        self.assertEqual(rows[self.ground_two.id], 1)

        detail_response = self.client.get(f'/dashboard/admin/invoices/{invoice.id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'FB-INV-')
        self.assertContains(detail_response, 'Line Items')

    def test_admin_mark_paid_and_unpaid_updates_settlement_metadata(self):
        invoice = GroundInvoice.objects.create(
            ground=self.ground_one,
            period_start=self.settlement_date,
            period_end=self.settlement_date,
            bookings_count=1,
            charge_per_booking=100,
            total_amount=100,
            is_paid=False,
        )

        self.client.force_login(self.admin)
        paid_response = self.client.post('/dashboard/admin/invoices/mark-paid/', {'invoice_id': str(invoice.id)})
        self.assertEqual(paid_response.status_code, 200)

        invoice.refresh_from_db()
        self.assertTrue(invoice.is_paid)
        self.assertIsNotNone(invoice.settled_at)
        self.assertEqual(invoice.settled_by, self.admin)

        unpaid_response = self.client.post('/dashboard/admin/invoices/mark-unpaid/', {'invoice_id': str(invoice.id)})
        self.assertEqual(unpaid_response.status_code, 200)

        invoice.refresh_from_db()
        self.assertFalse(invoice.is_paid)
        self.assertIsNone(invoice.settled_at)
        self.assertIsNone(invoice.settled_by)

    def test_admin_creates_online_settlement_and_owner_acknowledges_receipt(self):
        online_slot_one = Slot.objects.create(
            ground=self.ground_one,
            date=self.settlement_date,
            start_time=time(13, 0),
            end_time=time(14, 0),
            is_booked=True,
        )
        online_slot_two = Slot.objects.create(
            ground=self.ground_one,
            date=self.settlement_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=online_slot_one,
            customer_name='Online User 1',
            customer_phone='9000000003',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )
        Booking.objects.create(
            slot=online_slot_two,
            customer_name='Online User 2',
            customer_phone='9000000004',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='PARTIAL_99',
            payment_status='PARTIALLY_PAID',
            paid_amount=99,
            due_amount=401,
        )

        self.client.force_login(self.admin)
        response = self.client.post('/dashboard/admin/online-settlements/', {
            'ground_id': str(self.ground_one.id),
            'period_start': self.settlement_date.strftime('%Y-%m-%d'),
            'period_end': self.settlement_date.strftime('%Y-%m-%d'),
            'admin_note': 'July online transfer',
        })
        self.assertEqual(response.status_code, 302)

        settlement = OnlineSettlement.objects.get(ground=self.ground_one)
        self.assertEqual(settlement.booking_count, 2)
        self.assertEqual(settlement.collected_amount, Decimal('599.00'))
        self.assertEqual(settlement.status, 'CREATED')
        self.assertEqual(OnlineSettlementLineItem.objects.filter(settlement=settlement).count(), 2)
        self.assertEqual(Booking.objects.get(slot=online_slot_one).online_settlement, settlement)
        self.assertEqual(Booking.objects.get(slot=online_slot_two).online_settlement, settlement)

        self.client.force_login(self.admin)
        transfer_response = self.client.post(f'/dashboard/admin/online-settlements/{settlement.id}/transferred/')
        self.assertEqual(transfer_response.status_code, 302)

        settlement.refresh_from_db()
        self.assertEqual(settlement.status, 'TRANSFERRED')
        self.assertIsNotNone(settlement.transferred_at)
        self.assertEqual(settlement.transferred_by, self.admin)

        self.client.force_login(self.owner)
        owner_response = self.client.get('/dashboard/owner/online-settlements/')
        self.assertEqual(owner_response.status_code, 200)
        self.assertContains(owner_response, settlement.reference)

        ack_response = self.client.post('/dashboard/owner/online-settlements/', {
            'settlement_id': str(settlement.id),
            'action': 'ACKNOWLEDGE',
            'note': 'Received in account',
        })
        self.assertEqual(ack_response.status_code, 302)

        settlement.refresh_from_db()
        self.assertEqual(settlement.status, 'ACKNOWLEDGED')
        self.assertEqual(settlement.owner_confirmed_by, self.owner)
        self.assertIsNotNone(settlement.owner_confirmed_at)

    def test_admin_online_settlements_page_renders_submit_form(self):
        settlement_slot = Slot.objects.create(
            ground=self.ground_one,
            date=self.settlement_date,
            start_time=time(13, 0),
            end_time=time(14, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=settlement_slot,
            customer_name='Online User',
            customer_phone='9000000099',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
        )

        self.client.force_login(self.admin)
        response = self.client.get(
            f'/dashboard/admin/online-settlements/?start={self.settlement_date.strftime("%Y-%m-%d")}&end={self.settlement_date.strftime("%Y-%m-%d")}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'action="/dashboard/admin/online-settlements/"')
        self.assertContains(response, 'data-processing-overlay="true"')
        self.assertContains(response, 'data-inline-loading="true"')
        self.assertContains(response, 'data-inline-submit-button')
        self.assertContains(response, 'data-inline-spinner')


class BookingFraudDetectionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='fraudowner@example.com',
            phone_number='6111111111',
            name='Fraud Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.customer = User.objects.create_user(
            email='fraudcustomer@example.com',
            phone_number='6222222222',
            name='Fraud Customer',
            password='password123',
            role='customer',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='Fraud Arena',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=900,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )
        self.slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(8, 0),
            end_time=time(9, 0),
            is_booked=False,
        )

    def _mock_razorpay_client(self, *, user_id, slot_id, amount_paise):
        class _Utility:
            @staticmethod
            def verify_payment_signature(_):
                return None

        class _Order:
            @staticmethod
            def fetch(order_id):
                return {
                    'id': order_id,
                    'notes': {'slot_id': str(slot_id), 'user_id': str(user_id)},
                }

        class _Payment:
            @staticmethod
            def fetch(_):
                return {
                    'order_id': 'order_test_1',
                    'status': 'captured',
                    'amount': amount_paise,
                }

        class _Client:
            utility = _Utility()
            order = _Order()
            payment = _Payment()

        return _Client()

    def test_verify_payment_blocks_user_mismatch(self):
        self.client.force_login(self.customer)
        fake_client = self._mock_razorpay_client(
            user_id=999999,  # wrong user on purpose
            slot_id=self.slot.id,
            amount_paise=50000,
        )
        payload = {
            'slot_id': self.slot.id,
            'payment_mode': 'FULL',
            'razorpay_order_id': 'order_test_1',
            'razorpay_payment_id': 'pay_test_1',
            'razorpay_signature': 'sig_test_1',
        }
        with patch('bookings.views._razorpay_client', return_value=(fake_client, 'rzp_test_key')):
            response = self.client.post(
                '/payments/razorpay/verify-and-book/',
                data=payload,
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('User mismatch', response.json().get('error', ''))
        self.assertFalse(Booking.objects.filter(slot=self.slot, status='BOOKED').exists())

    def test_verify_payment_blocks_amount_mismatch(self):
        self.client.force_login(self.customer)
        fake_client = self._mock_razorpay_client(
            user_id=self.customer.id,
            slot_id=self.slot.id,
            amount_paise=10000,  # wrong amount for full payment
        )
        payload = {
            'slot_id': self.slot.id,
            'payment_mode': 'FULL',
            'razorpay_order_id': 'order_test_1',
            'razorpay_payment_id': 'pay_test_1',
            'razorpay_signature': 'sig_test_1',
        }
        with patch('bookings.views._razorpay_client', return_value=(fake_client, 'rzp_test_key')):
            response = self.client.post(
                '/payments/razorpay/verify-and-book/',
                data=payload,
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Paid amount mismatch', response.json().get('error', ''))
        self.assertFalse(Booking.objects.filter(slot=self.slot, status='BOOKED').exists())
