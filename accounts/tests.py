from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking, Slot
from grounds.models import Ground


class AdminDashboardSettlementSplitTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com',
            phone_number='9999990000',
            name='Admin',
            password='password123',
            role='admin',
            email_verified=True,
        )
        self.owner = User.objects.create_user(
            email='owner@example.com',
            phone_number='8888880000',
            name='Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.customer = User.objects.create_user(
            email='customer@example.com',
            phone_number='7777770000',
            name='Customer',
            password='password123',
            role='customer',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='Admin Test Ground',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=700,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )

    def test_admin_dashboard_monthly_online_manual_split(self):
        today = timezone.localdate()
        online_slot = Slot.objects.create(
            ground=self.ground,
            date=today,
            start_time=time(8, 0),
            end_time=time(9, 0),
            is_booked=True,
        )
        manual_slot = Slot.objects.create(
            ground=self.ground,
            date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=online_slot,
            user=self.customer,
            customer_name='Online User',
            customer_phone='7000000001',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=500,
            due_amount=0,
            status='BOOKED',
        )
        Booking.objects.create(
            slot=manual_slot,
            customer_name='Walk-in User',
            customer_phone='7000000002',
            total_amount=700,
            owner_payout=700,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PARTIALLY_PAID',
            paid_amount=200,
            due_amount=500,
            status='BOOKED',
        )

        self.client.force_login(self.admin)
        response = self.client.get('/accounts/admin-dashboard/')
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['month_online_bookings'], 1)
        self.assertEqual(response.context['month_online_collected'], 500)
        self.assertEqual(response.context['month_online_due'], 0)
        self.assertEqual(response.context['month_manual_bookings'], 1)
        self.assertEqual(response.context['month_manual_collected'], 200)
        self.assertEqual(response.context['month_manual_due'], 500)
