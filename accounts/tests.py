import json
from datetime import time, timedelta

from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import CustomerLoginOTP, User
from bookings.models import Booking, Slot
from grounds.models import Ground
from bookings.models import EmailVerification
from django.contrib.auth.hashers import check_password
from bookings.whatsapp import send_customer_login_otp


@override_settings(CUSTOMER_WHATSAPP_OTP_ENABLED=True)
class WhatsAppOTPLoginTests(TestCase):
    def test_new_customer_can_log_in_with_whatsapp_otp(self):
        with patch('accounts.views.send_customer_login_otp', return_value=True) as send_otp:
            response = self.client.post(
                '/accounts/login/', {'phone': '9876543210'},
                REMOTE_ADDR='103.14.50.224:23331',
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['otp_sent'])
        record = CustomerLoginOTP.objects.get(phone_number='9876543210')
        self.assertEqual(record.requested_ip, '103.14.50.224')
        otp = send_otp.call_args.args[1]
        self.assertTrue(check_password(otp, record.code_hash))

        response = self.client.post('/accounts/login/verify-otp/', {
            'phone': '9876543210', 'otp': otp,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/accounts/customer-dashboard/')
        user = User.objects.get(phone_number='9876543210')
        self.assertEqual(user.role, 'customer')
        self.assertTrue(user.email_verified)

    def test_wrong_otp_does_not_log_customer_in(self):
        with patch('accounts.views.send_customer_login_otp', return_value=True):
            self.client.post('/accounts/login/', {'phone': '9876543210'})

        response = self.client.post('/accounts/login/verify-otp/', {
            'phone': '9876543210', 'otp': '000000',
        })
        self.assertRedirects(response, '/accounts/login/?phone=9876543210')
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_otp_send_failure_creates_no_customer_or_code(self):
        with patch('accounts.views.send_customer_login_otp', return_value=False):
            response = self.client.post('/accounts/login/', {'phone': '9876543210'})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(phone_number='9876543210').exists())
        self.assertFalse(CustomerLoginOTP.objects.filter(phone_number='9876543210').exists())

    def test_otp_database_error_stays_on_whatsapp_login(self):
        with patch('accounts.views.CustomerLoginOTP.objects.filter', side_effect=DatabaseError('database unavailable')):
            response = self.client.post('/accounts/login/', {
                'phone': '9876543210', 'next': '/grounds/12/?date=2026-07-21',
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'WhatsApp login is temporarily unavailable')

    def test_unexpected_otp_failure_stays_on_whatsapp_login(self):
        with patch('accounts.views.send_customer_login_otp', side_effect=RuntimeError('provider unavailable')):
            response = self.client.post('/accounts/login/', {'phone': '9876543210'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'We could not start WhatsApp login')

    def test_successful_otp_never_redirects_back_to_an_email_login_url(self):
        with patch('accounts.views.send_customer_login_otp', return_value=True) as send_otp:
            self.client.post('/accounts/login/', {'phone': '9876543210'})
        otp = send_otp.call_args.args[1]

        response = self.client.post('/accounts/login/verify-otp/', {
            'phone': '9876543210', 'otp': otp,
            'next': '/accounts/email-login/',
        })
        self.assertRedirects(response, '/accounts/customer-dashboard/', fetch_redirect_response=False)

    def test_login_page_includes_public_available_bookings_panel(self):
        response = self.client.get('/accounts/login/')
        self.assertContains(response, 'Available bookings')
        self.assertContains(response, 'login-availability.js')


class EmailMagicLinkLoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='player@example.com', phone_number='9876543210', name='Player',
            password='unused-password', role='customer', email_verified=False,
        )

    def test_email_link_logs_the_user_in_and_returns_to_the_selected_ground(self):
        next_url = '/grounds/12/?date=2026-07-21'
        with patch('accounts.views.send_mail') as send_mail:
            response = self.client.post('/accounts/email-login/', {
                'email': self.user.email,
                'next': next_url,
            })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'secure sign-in link')
        verification = EmailVerification.objects.get(user=self.user)
        body = send_mail.call_args.args[1]
        self.assertIn('next=/grounds/12/%3Fdate%3D2026-07-21', body)

        response = self.client.get(f'/accounts/verify-email/{verification.token}/?next=/grounds/12/%3Fdate%3D2026-07-21')
        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertEqual(str(self.client.session['_auth_user_id']), str(self.user.id))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)


class WhatsAppTemplatePayloadTests(TestCase):
    @override_settings(
        WHATSAPP_ENABLED=True,
        WHATSAPP_ACCESS_TOKEN='test-token',
        WHATSAPP_PHONE_NUMBER_ID='123',
        WHATSAPP_OTP_TEMPLATE_NAME='footbook_login_otp',
    )
    @patch('bookings.whatsapp.urlopen')
    def test_otp_template_includes_its_required_dynamic_url_button_parameter(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.status = 200

        self.assertTrue(send_customer_login_otp('9876543210', '123456'))
        payload = json.loads(urlopen.call_args.args[0].data.decode('utf-8'))
        self.assertEqual(payload['template']['components'][0]['parameters'][0]['text'], '123456')
        self.assertEqual(payload['template']['components'][1], {
            'type': 'button', 'sub_type': 'url', 'index': '0',
            'parameters': [{'type': 'text', 'text': '123456'}],
        })


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

    def test_admin_can_toggle_owner_whatsapp_booking_updates(self):
        self.assertFalse(self.owner.whatsapp_booking_updates_enabled)

        response = self.client.post(
            f'/accounts/ground-owner/{self.owner.id}/whatsapp-booking-updates-toggle/'
        )

        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.whatsapp_booking_updates_enabled)


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
