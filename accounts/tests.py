from datetime import time, timedelta

from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.utils import timezone

from accounts.models import User
from bookings.models import Booking, Slot
from grounds.models import Ground
from bookings.models import EmailVerification


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

    def test_admin_dashboard_keeps_online_and_ground_collections_separate(self):
        today = timezone.localdate()
        partial_slot = Slot.objects.create(
            ground=self.ground,
            date=today,
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=partial_slot,
            user=self.customer,
            customer_name='Partial Online User',
            customer_phone='7000000003',
            total_amount=500,
            owner_payout=500,
            booking_source='ONLINE',
            payment_mode='PARTIAL_99',
            payment_status='PAID_AT_GROUND',
            paid_amount=500,
            due_amount=0,
            status='BOOKED',
        )

        self.client.force_login(self.admin)
        response = self.client.get('/accounts/admin-dashboard/')
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['month_online_collected'], 99)
        self.assertEqual(response.context['month_online_collected_at_ground'], 401)
        self.assertEqual(response.context['month_online_due'], 0)

    def test_admin_dashboard_orders_grounds_by_income(self):
        today = timezone.localdate()
        second_ground = Ground.objects.create(
            name='Admin Test Ground 2',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=700,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )
        slot_one = Slot.objects.create(
            ground=self.ground,
            date=today,
            start_time=time(12, 0),
            end_time=time(13, 0),
            is_booked=True,
        )
        slot_two = Slot.objects.create(
            ground=second_ground,
            date=today,
            start_time=time(14, 0),
            end_time=time(15, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=slot_one,
            user=self.customer,
            customer_name='Ground One',
            customer_phone='7000000101',
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
            slot=slot_two,
            user=self.customer,
            customer_name='Ground Two',
            customer_phone='7000000102',
            total_amount=900,
            owner_payout=900,
            booking_source='ONLINE',
            payment_mode='FULL',
            payment_status='PAID',
            paid_amount=900,
            due_amount=0,
            status='BOOKED',
        )

        self.client.force_login(self.admin)
        response = self.client.get('/accounts/admin-dashboard/')
        self.assertEqual(response.status_code, 200)

        ranking = list(response.context['ground_income_ranking'])
        self.assertEqual(ranking[0]['slot__ground__name'], 'Admin Test Ground 2')
        self.assertEqual(ranking[0]['revenue'], 900)


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class RegistrationResilienceTests(TestCase):
    @patch('accounts.views.send_mail', side_effect=Exception('SMTP down'))
    def test_register_succeeds_when_email_sending_fails(self, mocked_send_mail):
        response = self.client.post('/accounts/register/', {
            'email': 'newuser@example.com',
            'phone_number': '9999912345',
            'name': 'New User',
            'password': 'password123',
            'password_confirm': 'password123',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
        self.assertTrue(EmailVerification.objects.filter(user__email='newuser@example.com').exists())
        self.assertContains(response, 'wa.me/918625877270')
        self.assertContains(response, 'newuser%40example.com')

    def test_register_page_hides_referral_code_field(self):
        response = self.client.get('/accounts/register/')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Referral Code')
        self.assertNotContains(response, 'referral_code')

    def test_verify_email_auto_logs_user_in(self):
        user = User.objects.create_user(
            email='verifyme@example.com',
            phone_number='9999912346',
            name='Verify Me',
            password='password123',
            role='customer',
            email_verified=False,
        )
        verification = EmailVerification.objects.create(user=user)

        response = self.client.get(f'/accounts/verify-email/{verification.token}/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)

    def test_login_page_shows_one_time_registration_popup(self):
        response = self.client.get('/accounts/login/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'releaseNotesModal')
        self.assertContains(response, 'Create Free Account')
        self.assertContains(response, 'slot discounts')
        self.assertContains(response, 'free booking credits')
        self.assertContains(response, 'data-release-notes-version="2026-07-16-v1"')


class CsrfFailurePageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com',
            phone_number='8888880000',
            name='Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='CSRF Ground',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=700,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )

    def test_custom_csrf_failure_page_shows_support_link(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post('/owner/manual-booking/', {
            'ground': str(self.ground.id),
            'date': timezone.localdate().strftime('%Y-%m-%d'),
            'slot': '1',
            'name': 'Test',
            'phone': '9999911111',
        })

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Report via WhatsApp', status_code=403)
        self.assertContains(response, 'Request blocked', status_code=403)
