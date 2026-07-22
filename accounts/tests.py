import json
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


class AdminGroundCrudTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin-crud@example.com',
            phone_number='9999990101',
            name='Admin',
            password='password123',
            role='admin',
            email_verified=True,
        )
        self.owner = User.objects.create_user(
            email='owner-crud@example.com',
            phone_number='8888880101',
            name='Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )
        self.ground = Ground.objects.create(
            name='CRUD Ground',
            location='City',
            owner=self.owner,
            day_price=500,
            night_price=700,
            opening_time=time(6, 0),
            closing_time=time(23, 0),
        )
        self.client.force_login(self.admin)

    def test_admin_can_edit_ground_rates(self):
        response = self.client.post(f'/accounts/ground/{self.ground.id}/edit/', {
            'name': 'Edited Ground',
            'location': 'Margao',
            'opening_time': '06:00',
            'closing_time': '02:00',
            'slot_1_start': '06:00',
            'slot_1_end': '12:00',
            'slot_1_price': '400',
            'slot_2_start': '12:00',
            'slot_2_end': '15:00',
            'slot_2_price': '800',
            'slot_3_start': '15:00',
            'slot_3_end': '22:00',
            'slot_3_price': '1000',
            'slot_4_start': '22:00',
            'slot_4_end': '02:00',
            'slot_4_price': '700',
        })

        self.assertEqual(response.status_code, 302)
        self.ground.refresh_from_db()
        self.assertEqual(self.ground.name, 'Edited Ground')
        self.assertEqual(self.ground.groundpricing_set.count(), 4)
        self.assertTrue(
            self.ground.groundpricing_set.filter(
                start_time=time(22, 0),
                end_time=time(2, 0),
                price_per_hour=700,
            ).exists()
        )

    def test_admin_can_save_any_number_of_connected_rate_blocks(self):
        response = self.client.post(f'/accounts/ground/{self.ground.id}/edit/', {
            'name': 'Five Rate Ground',
            'location': 'Margao',
            'opening_time': '06:00',
            'closing_time': '02:00',
            'rate_blocks': json.dumps([
                {'start': '06:00', 'end': '09:00', 'price': 400},
                {'start': '09:00', 'end': '12:00', 'price': 500},
                {'start': '12:00', 'end': '16:00', 'price': 600},
                {'start': '16:00', 'end': '22:00', 'price': 900},
                {'start': '22:00', 'end': '02:00', 'price': 700},
            ]),
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.ground.groundpricing_set.count(), 5)
        self.assertTrue(self.ground.groundpricing_set.filter(
            start_time=time(22, 0), end_time=time(2, 0), price_per_hour=700,
        ).exists())

    def test_admin_can_delete_ground_without_booking_history(self):
        response = self.client.post(f'/accounts/ground/{self.ground.id}/delete/')

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Ground.objects.filter(id=self.ground.id).exists())

    def test_admin_cannot_delete_ground_with_booking_history(self):
        slot = Slot.objects.create(
            ground=self.ground,
            date=timezone.localdate(),
            start_time=time(8, 0),
            end_time=time(9, 0),
            is_booked=True,
        )
        Booking.objects.create(
            slot=slot,
            customer_name='Booked User',
            customer_phone='7000000000',
            total_amount=500,
            owner_payout=500,
            booking_source='MANUAL',
            payment_mode='FULL',
            payment_status='PENDING',
            paid_amount=0,
            due_amount=500,
            status='BOOKED',
        )

        response = self.client.post(f'/accounts/ground/{self.ground.id}/delete/')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ground.objects.filter(id=self.ground.id).exists())

    def test_admin_can_edit_and_delete_owner_without_grounds(self):
        owner = User.objects.create_user(
            email='empty-owner@example.com',
            phone_number='8888880202',
            name='Empty Owner',
            password='password123',
            role='owner',
            email_verified=True,
        )

        edit_response = self.client.post(f'/accounts/ground-owner/{owner.id}/edit/', {
            'name': 'Updated Owner',
            'email': 'updated-owner@example.com',
            'phone_number': '8888880303',
        })
        self.assertEqual(edit_response.status_code, 302)
        owner.refresh_from_db()
        self.assertEqual(owner.name, 'Updated Owner')

        delete_response = self.client.post(f'/accounts/ground-owner/{owner.id}/delete/')
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(User.objects.filter(id=owner.id).exists())


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

    def test_login_page_sets_csrf_cookie(self):
        response = self.client.get('/accounts/login/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
        self.assertTrue(response.cookies['csrftoken'].value)

    def test_csrf_failed_login_with_valid_credentials_recovers_session(self):
        user = User.objects.create_user(
            email='csrf-user@example.com',
            phone_number='9999912347',
            name='CSRF User',
            password='password123',
            role='customer',
            email_verified=False,
        )
        EmailVerification.objects.create(user=user)
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post('/accounts/login/?next=/', {
            'email': 'csrf-user@example.com',
            'password': 'password123',
            'next': '/',
        }, HTTP_REFERER='http://footbook.online/accounts/login/?next=/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are signed in')
        self.assertContains(response, 'Report via WhatsApp')
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(int(csrf_client.session['_auth_user_id']), user.id)
        self.assertTrue(EmailVerification.objects.filter(user=user, is_verified=True).exists())

    def test_csrf_failed_login_with_invalid_credentials_stays_blocked(self):
        user = User.objects.create_user(
            email='csrf-invalid@example.com',
            phone_number='9999912348',
            name='CSRF Invalid',
            password='password123',
            role='customer',
            email_verified=False,
        )
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post('/accounts/login/', {
            'email': 'csrf-invalid@example.com',
            'password': 'wrong-password',
        }, HTTP_REFERER='http://footbook.online/accounts/login/')

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'We could not verify your request', status_code=403)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
        self.assertNotIn('_auth_user_id', csrf_client.session)


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

    def test_login_csrf_failure_shows_retry_link(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/accounts/login/', {
            'email': 'missing@example.com',
            'password': 'password123',
            'next': '/',
        })

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Continue to Login', status_code=403)
        self.assertContains(response, 'missing%40example.com', status_code=403)
        self.assertContains(response, 'Your browser blocked the login submission', status_code=403)
