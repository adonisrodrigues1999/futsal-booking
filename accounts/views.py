import logging
import secrets
import re
import ipaddress
import uuid
from urllib.parse import quote

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.forms import SetPasswordForm
from datetime import timedelta
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce
from django import forms
from .models import User, CustomerLoginOTP
from bookings.whatsapp import send_customer_login_otp
from django.contrib.auth.hashers import check_password, make_password
from bookings.models import EmailVerification
from bookings.models import Booking
from bookings.money import ground_collected_amount_expression, online_collected_amount_expression
from bookings.slot_generation import create_initial_slots_for_ground
from .forms import EmailMagicLinkForm, UserRegistrationForm, UserLoginForm, GroundOwnerCreationForm, GroundOwnerEditForm, GroundCreationForm, CustomerProfileForm
from grounds.models import Ground, Tournament, TournamentRegistration


logger = logging.getLogger(__name__)
WHATSAPP_SUPPORT_NUMBER = "918625877270"


def _whatsapp_support_link(*, email, verification_url):
    message = (
        "Hi FootBook, my verification email did not arrive.\n\n"
        f"Registered email: {email}\n"
        f"Verification link: {verification_url}\n\n"
        "Please help me verify my account."
    )
    return f"https://wa.me/{WHATSAPP_SUPPORT_NUMBER}?text={quote(message)}"


def _build_support_issue_link(*, request, reason):
    user = getattr(request, 'user', None)
    user_name = getattr(user, 'name', '') if user and getattr(user, 'is_authenticated', False) else ''
    user_email = getattr(user, 'email', '') if user and getattr(user, 'is_authenticated', False) else ''
    submitted_identifier = ''
    if request.method == 'POST':
        submitted_identifier = (
            request.POST.get('email')
            or request.POST.get('phone')
            or ''
        ).strip()
    message = (
        "Hi FootBook, I hit a production error.\n\n"
        f"Reason: {reason}\n"
        f"User: {user_name or '-'}\n"
        f"Email: {user_email or (submitted_identifier if '@' in submitted_identifier else '-')}\n"
        f"Login identifier: {submitted_identifier or '-'}\n"
        f"Path: {request.path}\n"
        f"Method: {request.method}\n"
        f"Referer: {request.META.get('HTTP_REFERER', '-')}\n"
        f"User-Agent: {request.META.get('HTTP_USER_AGENT', '-')}\n"
        f"IP: {request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '-'))}\n"
        "\nPlease check the platform logs and recent booking activity."
    )
    return f"https://wa.me/{WHATSAPP_SUPPORT_NUMBER}?text={quote(message)}"


def _safe_next_url(request, next_url):
    if not next_url:
        return ''
    return next_url if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ) else ''


def _post_login_redirect_url(request, user, *, next_url='', slot_id=''):
    if slot_id:
        try:
            from bookings.models import Slot
            slot = Slot.objects.select_related('ground').get(id=slot_id)
            return f'/grounds/{slot.ground.id}/?date={slot.date}'
        except Exception:
            logger.exception("Unable to build slot redirect for login slot_id=%s", slot_id)

    safe_next = _safe_next_url(request, next_url)
    login_paths = {reverse('login'), reverse('email_login')}
    if safe_next and safe_next.split('?', 1)[0] not in login_paths:
        return safe_next

    if user.role == 'admin':
        return reverse('admin_dashboard')
    if user.role == 'owner':
        return reverse('owner_dashboard')
    return reverse('customer_dashboard')


def _normalise_indian_phone(value):
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    return digits if re.fullmatch(r'[6-9]\d{9}', digits) else ''


def _normalise_customer_name(value):
    name = ' '.join((value or '').split())
    return name if 2 <= len(name) <= 100 else ''


def _request_ip(request):
    raw_address = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR', '').strip()
    )
    if not raw_address:
        return None
    try:
        return str(ipaddress.ip_address(raw_address))
    except ValueError:
        # Azure commonly supplies REMOTE_ADDR as IPv4:port.  Keep IPv6 intact
        # and only remove a port after proving the host is a valid address.
        if raw_address.count(':') == 1:
            host, _, _port = raw_address.partition(':')
            try:
                return str(ipaddress.ip_address(host))
            except ValueError:
                pass
    logger.warning('Ignoring invalid client IP address for OTP request: %r', raw_address)
    return None


def _email_login_url(*, next_url='', slot_id=''):
    query_bits = []
    if next_url:
        query_bits.append(f'next={quote(next_url)}')
    if slot_id:
        query_bits.append(f'slot={quote(str(slot_id))}')
    return f"{reverse('email_login')}?{'&'.join(query_bits)}" if query_bits else reverse('email_login')


def _send_email_login_link(*, request, user, name, next_url='', slot_id=''):
    """Create a fresh, single-use link and email it to an existing account."""
    verification, _ = EmailVerification.objects.get_or_create(user=user)
    verification.token = uuid.uuid4()
    verification.is_verified = False
    verification.save(update_fields=['token', 'is_verified'])
    verification_url = request.build_absolute_uri(reverse('verify_email', args=[verification.token]))
    query_bits = [f'name={quote(name)}']
    if next_url:
        query_bits.append(f'next={quote(next_url)}')
        if slot_id:
            query_bits.append(f'slot={quote(str(slot_id))}')
    elif slot_id:
        query_bits.append(f'slot={quote(str(slot_id))}')
    verification_url = f"{verification_url}?{'&'.join(query_bits)}"
    send_mail(
        'Your FootBook sign-in link',
        (
            'Use this secure link to sign in to FootBook:\n\n'
            f'{verification_url}\n\n'
            'This link signs you in directly. If you did not request it, you can ignore this email.'
        ),
        getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
        [user.email],
        fail_silently=False,
    )


def _customer_for_verified_phone(phone, name):
    """Return the existing customer, or create one only after OTP verification."""
    user = User.objects.filter(phone_number=phone).first()
    if user:
        if user.name != name:
            user.name = name
            user.save(update_fields=['name'])
        return user
    # The existing user schema requires an email. This internal placeholder is
    # never used for notifications and can be replaced from the profile later.
    try:
        with transaction.atomic():
            user = User(
                email=f'{phone}@otp.footbook.online', phone_number=phone,
                name=name, role='customer', email_verified=True,
            )
            user.set_unusable_password()
            user.save()
            return user
    except IntegrityError:
        return User.objects.get(phone_number=phone)


def _recover_login_after_csrf_failure(request):
    if request.path != reverse('login') or request.method != 'POST':
        return None

    form = UserLoginForm(request.POST)
    if not form.is_valid():
        return None

    email = form.cleaned_data.get('email')
    phone = form.cleaned_data.get('phone')
    password = form.cleaned_data['password']
    user_obj = None
    user = None

    try:
        if email:
            user_obj = User.objects.get(email__iexact=email)
        elif phone:
            user_obj = User.objects.get(phone_number=phone)
    except User.DoesNotExist:
        return None

    if user_obj is not None:
        user = authenticate(request, username=user_obj.email, password=password)
    if user is None:
        return None

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])
        EmailVerification.objects.filter(user=user).update(is_verified=True)
        logger.warning("Auto-verified email during CSRF login recovery for user_id=%s", user.id)

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return _post_login_redirect_url(
        request,
        user,
        next_url=request.POST.get('next', ''),
        slot_id=request.POST.get('slot', ''),
    )


def csrf_failure(request, reason=""):
    recovered_redirect_url = _recover_login_after_csrf_failure(request)
    submitted_identifier = ''
    if request.method == 'POST':
        submitted_identifier = (
            request.POST.get('email')
            or request.POST.get('phone')
            or ''
        ).strip()
    logger.warning(
        "CSRF failure path=%s method=%s reason=%s referer=%s user_agent=%s ip=%s identifier=%s recovered=%s",
        request.path,
        request.method,
        reason or "CSRF verification failed",
        request.META.get('HTTP_REFERER', '-'),
        request.META.get('HTTP_USER_AGENT', '-'),
        request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '-')),
        submitted_identifier or '-',
        bool(recovered_redirect_url),
    )

    retry_login_url = None
    login_prompt = None
    if recovered_redirect_url:
        login_prompt = (
            'We verified your login details, marked your email as verified, and signed you in. '
            'This issue has been logged for FootBook support. You will be redirected automatically.'
        )
    elif request.path == reverse('login') and request.method == 'POST':
        identifier = submitted_identifier or request.GET.get('identifier', '').strip()
        next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
        retry_login_url = reverse('login')
        query_bits = []
        if identifier:
            query_bits.append(f'identifier={quote(identifier)}')
            login_prompt = (
                'Your browser blocked the login submission. '
                'Continue to login after reporting the issue; your details are preserved.'
            )
        if next_url:
            query_bits.append(f'next={quote(next_url)}')
        if query_bits:
            retry_login_url = f"{retry_login_url}?{'&'.join(query_bits)}"

    support_link = _build_support_issue_link(
        request=request,
        reason=reason or "CSRF verification failed",
    )
    return render(request, 'errors/csrf_failure.html', {
        'reason': reason or 'CSRF verification failed',
        'support_link': support_link,
        'retry_login_url': retry_login_url,
        'login_prompt': login_prompt,
        'recovered_redirect_url': recovered_redirect_url,
    }, status=200 if recovered_redirect_url else 403)


def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        # Normalise raw values before form validation so we catch duplicates early.
        raw_email = (request.POST.get('email') or '').strip().lower()
        raw_phone = (request.POST.get('phone_number') or '').strip()
        if raw_phone.startswith('+91'):
            raw_phone = raw_phone[3:]
        elif raw_phone.startswith('91') and len(raw_phone) > 10:
            raw_phone = raw_phone[2:]

        if raw_email:
            existing = User.objects.filter(email__iexact=raw_email).first()
            if existing:
                if existing.email_verified:
                    messages.info(
                        request,
                        'An account with this email already exists and is verified. Please login instead.'
                    )
                else:
                    messages.info(
                        request,
                        'An account with this email already exists but is not yet verified. '
                        'Please check your inbox for the verification link or login to resend it.'
                    )
                return redirect(f"{reverse('login')}?identifier={raw_email}")

        if raw_phone:
            if User.objects.filter(phone_number=raw_phone).exists():
                messages.info(
                    request,
                    'An account with this phone number already exists. Please login instead.'
                )
                return redirect(f"{reverse('login')}?identifier={raw_phone}")

        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            phone = form.cleaned_data.get('phone_number')

            user = form.save(commit=False)
            user.email_verified = False
            user.save()

            # Create email verification token
            verification = EmailVerification.objects.create(user=user)

            # Send verification email
            verification_url = request.build_absolute_uri(
                reverse('verify_email', args=[verification.token])
            )
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
            email_sent = False
            logger.info(
                "Register verification email attempt backend=%s from=%s to=%s",
                getattr(settings, 'EMAIL_BACKEND', 'unknown'),
                from_email,
                user.email,
            )
            try:
                send_mail(
                    'Verify your email - FootBook',
                    f'Click the link to verify your email: {verification_url}',
                    from_email,
                    [user.email],
                    fail_silently=False,
                )
                email_sent = True
                logger.info("Register verification email sent to %s", user.email)
            except Exception:
                logger.exception("Register verification email failed for %s", user.email)
                messages.warning(
                    request,
                    'Registration succeeded, but the verification email could not be sent right now. '
                    'You can use WhatsApp support if needed.'
                )

            whatsapp_support_link = _whatsapp_support_link(
                email=user.email,
                verification_url=verification_url,
            )

            # Instead of redirecting immediately, render the register page
            # and set a flag so the frontend shows a prominent popup and
            # then redirects the user to the login page.
            if email_sent:
                messages.success(
                    request,
                    'Registration successful! Please check your email to verify your account. '
                    'Also check your spam or junk folder if you do not see it in your inbox.'
                )
            else:
                messages.warning(
                    request,
                    'Registration successful! We could not send the verification email right now. '
                    'You can use WhatsApp support to get verified, or try logging in to resend the verification.'
                )
            form = UserRegistrationForm()
            return render(request, 'accounts/register.html', {
                'form': form,
                'show_verification_popup': True,
                'show_whatsapp_fallback': not email_sent,
                'whatsapp_support_link': whatsapp_support_link,
                'verification_message': (
                    'Registration successful! Please check your email to verify your account. '
                    'Also check your spam or junk folder if you do not see it in your inbox.'
                )
            })
    else:
        initial = {}
        email_param = request.GET.get('email', '')
        if email_param:
            initial['email'] = email_param
        form = UserRegistrationForm(initial=initial)

    return render(request, 'accounts/register.html', {'form': form})


@ensure_csrf_cookie
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    next_url = request.GET.get('next', '')
    slot_id_param = request.GET.get('slot', '')
    context = {'next': next_url, 'slot': slot_id_param, 'otp_sent': False}
    if request.method == 'POST':
        phone = _normalise_indian_phone(request.POST.get('phone'))
        name = _normalise_customer_name(request.POST.get('name'))
        next_url = request.POST.get('next', '')
        slot_id_param = request.POST.get('slot', '')
        context.update({'next': next_url, 'slot': slot_id_param})
        if not name:
            messages.error(request, 'Enter your name (at least 2 characters).')
        elif not phone:
            messages.error(request, 'Enter a valid 10-digit Indian mobile number.')
        elif not getattr(settings, 'CUSTOMER_WHATSAPP_OTP_ENABLED', True):
            messages.error(request, 'WhatsApp login is temporarily unavailable. Please use email login.')
        else:
            try:
                cutoff = timezone.now() - timedelta(minutes=15)
                if CustomerLoginOTP.objects.filter(phone_number=phone, created_at__gte=cutoff).count() >= 3:
                    messages.error(request, 'Too many OTP requests. Please wait 15 minutes and try again.')
                else:
                    CustomerLoginOTP.objects.filter(phone_number=phone, used_at__isnull=True).update(used_at=timezone.now())
                    otp = f'{secrets.randbelow(1_000_000):06d}'
                    record = CustomerLoginOTP.objects.create(
                        phone_number=phone, code_hash=make_password(otp),
                        expires_at=timezone.now() + timedelta(minutes=settings.CUSTOMER_OTP_EXPIRY_MINUTES),
                        requested_ip=_request_ip(request),
                    )
                    if send_customer_login_otp(phone, otp):
                        request.session['footbook_otp_id'] = record.id
                        request.session['footbook_otp_name'] = name
                        context.update({'otp_sent': True, 'phone': phone, 'name': name})
                        messages.success(request, 'Your OTP has been sent to WhatsApp.')
                    else:
                        record.delete()
                        logger.error('WhatsApp OTP send failed phone_ending=%s', phone[-4:])
                        messages.error(request, 'We could not send a WhatsApp OTP right now. Please use the email sign-in link or try again shortly.')
            except DatabaseError:
                # A transient database error (or a still-pending migration) must
                # never turn a login attempt into an unhelpful server error.
                logger.exception('WhatsApp OTP login database error phone_ending=%s', phone[-4:])
                messages.error(request, 'WhatsApp login is temporarily unavailable. Please try again shortly.')
            except Exception:
                # The WhatsApp provider is external to the authentication flow.
                # Keep an unexpected provider/configuration failure from exposing
                # a 500 page to a customer, while retaining the traceback in logs.
                logger.exception('WhatsApp OTP login failed phone_ending=%s', phone[-4:])
                messages.error(request, 'We could not start WhatsApp login. Please try again shortly.')
    return render(request, 'accounts/login.html', context)


@ensure_csrf_cookie
def verify_customer_otp(request):
    if request.method != 'POST':
        return redirect('login')
    phone = _normalise_indian_phone(request.POST.get('phone'))
    otp = (request.POST.get('otp') or '').strip()
    otp_id = request.session.get('footbook_otp_id')
    name = _normalise_customer_name(request.session.get('footbook_otp_name'))
    if not phone or not name or not re.fullmatch(r'\d{6}', otp) or not otp_id:
        messages.error(request, 'Enter the 6-digit OTP sent to your WhatsApp.')
        return redirect('login')
    with transaction.atomic():
        try:
            record = CustomerLoginOTP.objects.select_for_update().get(
                id=otp_id, phone_number=phone, used_at__isnull=True,
            )
        except CustomerLoginOTP.DoesNotExist:
            messages.error(request, 'That OTP is no longer valid. Request a new one.')
            return redirect('login')
        if record.expires_at <= timezone.now() or record.attempts >= settings.CUSTOMER_OTP_MAX_ATTEMPTS:
            record.used_at = timezone.now()
            record.save(update_fields=['used_at'])
            messages.error(request, 'That OTP expired. Request a new one.')
            return redirect('login')
        record.attempts += 1
        if not check_password(otp, record.code_hash):
            record.save(update_fields=['attempts'])
            messages.error(request, 'Incorrect OTP. Please try again.')
            return redirect(f'{reverse("login")}?phone={phone}')
        user = _customer_for_verified_phone(phone, name)
        record.user = user
        record.used_at = timezone.now()
        record.save(update_fields=['user', 'used_at', 'attempts'])
    request.session.pop('footbook_otp_id', None)
    request.session.pop('footbook_otp_name', None)
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(request, 'You are logged in.')
    return redirect(_post_login_redirect_url(request, user, next_url=request.POST.get('next', ''), slot_id=request.POST.get('slot', '')))


@ensure_csrf_cookie
def email_login_view(request):
    """Passwordless email sign-in for customers and staff."""
    if request.user.is_authenticated:
        return redirect(_post_login_redirect_url(request, request.user))

    next_url = request.POST.get('next', request.GET.get('next', ''))
    slot_id = request.POST.get('slot', request.GET.get('slot', ''))
    form = EmailMagicLinkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data['email']).first()
        if user and user.is_active:
            try:
                _send_email_login_link(
                    request=request, user=user, name=form.cleaned_data['name'],
                    next_url=next_url, slot_id=slot_id,
                )
            except Exception:
                logger.exception('Email login link failed user_id=%s', user.id)
                messages.error(request, 'We could not send the sign-in link right now. Please try again shortly.')
            else:
                messages.success(request, 'Check your email for a secure sign-in link. It will log you in directly.')
        else:
            # Keep the response neutral, while giving a legitimate new customer
            # a clear route to create the account that owns this email address.
            messages.info(request, 'If this email has a FootBook account, a sign-in link will arrive shortly. New here? Please register first.')
    return render(request, 'accounts/email_login.html', {
        'form': form,
        'next': next_url,
        'slot': slot_id,
        'whatsapp_login_url': f"{reverse('login')}?next={quote(next_url)}" if next_url else reverse('login'),
    })


def resend_verification(request):
    """Resend verification email for unverified accounts."""
    if request.method != 'POST':
        return redirect('login')

    email = request.POST.get('email', '').strip()
    if not email:
        messages.error(request, 'Please provide your email address.')
        return redirect('login')

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        messages.error(request, 'No account found with that email.')
        return redirect('login')

    if user.email_verified:
        messages.info(request, 'Your email is already verified. You can login.')
        return redirect('login')

    # Create a new verification token
    EmailVerification.objects.filter(user=user).delete()
    verification = EmailVerification.objects.create(user=user)

    verification_url = request.build_absolute_uri(
        reverse('verify_email', args=[verification.token])
    )
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)

    try:
        send_mail(
            'Verify your email - FootBook',
            f'Click the link to verify your email: {verification_url}',
            from_email,
            [user.email],
            fail_silently=False,
        )
        messages.success(
            request,
            'Verification email sent! Please check your inbox and spam folder.'
        )
    except Exception:
        logger.exception("Resend verification email failed for %s", user.email)
        messages.error(
            request,
            'Could not send verification email right now. Please try again later or use WhatsApp support.'
        )

    return redirect('login')


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


def verify_email(request, token):
    try:
        verification = EmailVerification.objects.get(token=token)
        if not verification.is_verified:
            verification.is_verified = True
            verification.save()
            verification.user.email_verified = True
            verification.user.save()
            messages.success(request, 'Email verified successfully! You are now logged in.')
        else:
            messages.info(request, 'Email already verified. You are now logged in.')

        name = _normalise_customer_name(request.GET.get('name'))
        if name and verification.user.name != name:
            verification.user.name = name
            verification.user.save(update_fields=['name'])
        login(request, verification.user, backend='django.contrib.auth.backends.ModelBackend')
        next_url = request.GET.get('next', '')
        slot_id = request.GET.get('slot', '')
        if not next_url and not slot_id:
            return redirect('home')
        return redirect(_post_login_redirect_url(
            request,
            verification.user,
            next_url=next_url,
            slot_id=slot_id,
        ))
    except EmailVerification.DoesNotExist:
        messages.error(request, 'Invalid verification link.')

    return redirect('login')


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))


def password_reset_request(request):
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                user = None

            # Always show the done page for security
            if user:
                token = PasswordResetTokenGenerator().make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                reset_url = request.build_absolute_uri(
                    reverse('password_reset_confirm', args=[uid, token])
                )
                subject = 'Reset your FootBook password'
                body = (
                    f'Hello {user.name},\n\n'
                    f'You requested a password reset. Click the link below to reset your password:\n\n{reset_url}\n\n'
                    'If you did not request this, you can ignore this email.\n\nRegards,\nFootBook'
                )
                from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
                try:
                    send_mail(subject, body, from_email, [user.email], fail_silently=False)
                except Exception:
                    # fail silently but continue to show success page
                    pass

            return redirect('password_reset_done')
    else:
        form = PasswordResetRequestForm()

    return render(request, 'accounts/password_reset.html', {'form': form})


def password_reset_done(request):
    return render(request, 'accounts/password_reset_done.html')


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None

    if user is None or not PasswordResetTokenGenerator().check_token(user, token):
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('password_reset')

    if request.method == 'POST':
        form = SetPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password reset successful. You can now log in.')
            return redirect('password_reset_complete')
    else:
        form = SetPasswordForm(user=user)

    form.fields['new_password1'].widget.attrs.update({'class': 'form-control'})
    form.fields['new_password2'].widget.attrs.update({'class': 'form-control'})

    return render(request, 'accounts/password_reset_confirm.html', {'form': form})


def password_reset_complete(request):
    return render(request, 'accounts/password_reset_complete.html')


def terms_conditions(request):
    return render(request, 'accounts/terms.html')


@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    ground_owners = User.objects.filter(role='owner').annotate(
        grounds_count=Count('ground', distinct=True),
    ).order_by('name', 'id')
    owner_filter = request.GET.get('owner')
    selected_owner = None
    grounds = Ground.objects.select_related('owner').prefetch_related('groundpricing_set').all()
    displayed_grounds = grounds
    if owner_filter:
        try:
            selected_owner = ground_owners.get(id=owner_filter)
            displayed_grounds = grounds.filter(owner=selected_owner)
        except (User.DoesNotExist, ValueError):
            selected_owner = None
    customers = User.objects.filter(role='customer')
    booked = Booking.objects.filter(status='BOOKED')

    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_bookings = booked.filter(slot__date__gte=month_start, slot__date__lte=today)
    month_sums = month_bookings.aggregate(
        gmv=Coalesce(Sum('total_amount'), 0),
        owner_payout=Coalesce(Sum('owner_payout'), 0),
    )
    month_online_sums = month_bookings.filter(booking_source='ONLINE').aggregate(
        bookings=Count('id'),
        paid=Coalesce(Sum(online_collected_amount_expression()), 0),
        due=Coalesce(Sum('due_amount'), 0),
        collected_at_ground=Coalesce(Sum(ground_collected_amount_expression()), 0),
        owner_payout=Coalesce(Sum('owner_payout'), 0),
    )
    month_manual_sums = month_bookings.filter(booking_source='MANUAL').aggregate(
        bookings=Count('id'),
        paid=Coalesce(Sum(ground_collected_amount_expression()), 0),
        due=Coalesce(Sum('due_amount'), 0),
        owner_payout=Coalesce(Sum('owner_payout'), 0),
    )
    month_gmv = int(month_sums['gmv'] or 0)
    month_owner_payout = int(month_sums['owner_payout'] or 0)
    month_platform_revenue = month_gmv - month_owner_payout

    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    trend_labels = [d.strftime('%Y-%m-%d') for d in days]
    trend_data = [booked.filter(slot__date=d).count() for d in days]

    top_grounds = (
        booked.values('slot__ground_id', 'slot__ground__name')
        .annotate(
            bookings_count=Count('id'),
            gmv=Coalesce(Sum('total_amount'), 0),
            owner_payout=Coalesce(Sum('owner_payout'), 0),
        )
        .order_by('-gmv', '-bookings_count')[:5]
    )
    for row in top_grounds:
        row['gmv'] = int(row['gmv'] or 0)
        row['platform_revenue'] = int((row['gmv'] or 0) - (row['owner_payout'] or 0))

    ground_income_ranking = (
        booked.values('slot__ground_id', 'slot__ground__name', 'slot__ground__owner__name')
        .annotate(
            bookings_count=Count('id'),
            revenue=Coalesce(Sum('owner_payout'), 0),
            gmv=Coalesce(Sum('total_amount'), 0),
        )
        .order_by('-revenue', '-bookings_count', 'slot__ground__name')
    )
    for row in ground_income_ranking:
        row['revenue'] = int(row['revenue'] or 0)
        row['gmv'] = int(row['gmv'] or 0)

    owner_leaderboard = (
        ground_owners
        .annotate(
            grounds_count=Count('ground', distinct=True),
            bookings_count=Count(
                'ground__slot__booking',
                filter=Q(ground__slot__booking__status='BOOKED'),
                distinct=True
            ),
            revenue=Coalesce(
                Sum('ground__slot__booking__owner_payout', filter=Q(ground__slot__booking__status='BOOKED')),
                0
            ),
        )
        .order_by('-bookings_count', '-revenue', 'name')[:8]
    )

    # Per-ground breakdown: total bookings & online money collected (all time + this month)
    per_ground_data = []
    for g in grounds:
        all_bookings = booked.filter(slot__ground=g)
        month_ground_bookings = month_bookings.filter(slot__ground=g)
        month_ground_online = month_ground_bookings.filter(booking_source='ONLINE')
        month_ground_manual = month_ground_bookings.filter(booking_source='MANUAL')
        total_bookings_count = all_bookings.count()
        month_bookings_count = month_ground_bookings.count()
        month_online_bookings_count = month_ground_online.count()
        month_online_collected = int(month_ground_online.aggregate(v=Coalesce(Sum(online_collected_amount_expression()), 0))['v'] or 0)
        month_manual_collected = int(month_ground_manual.aggregate(v=Coalesce(Sum(ground_collected_amount_expression()), 0))['v'] or 0)
        per_ground_data.append({
            'ground': g,
            'owner_name': g.owner.name if g.owner else '-',
            'total_bookings': total_bookings_count,
            'month_bookings': month_bookings_count,
            'month_online_bookings': month_online_bookings_count,
            'month_online_collected': month_online_collected,
            'month_manual_collected': month_manual_collected,
            'month_total_collected': month_online_collected + month_manual_collected,
        })

    context = {
        'ground_owners': ground_owners,
        'grounds': grounds,
        'displayed_grounds': displayed_grounds,
        'selected_owner': selected_owner,
        'customers': customers,
        'total_owners': ground_owners.count(),
        'total_grounds': grounds.count(),
        'total_customers': customers.count(),
        'month_bookings': month_bookings.count(),
        'month_gmv': month_gmv,
        'month_platform_revenue': month_platform_revenue,
        'month_online_bookings': int(month_online_sums['bookings'] or 0),
        'month_online_collected': int(month_online_sums['paid'] or 0),
        'month_online_due': int(month_online_sums['due'] or 0),
        'month_online_collected_at_ground': int(month_online_sums['collected_at_ground'] or 0),
        'month_online_owner_payable': int(month_online_sums['owner_payout'] or 0),
        'month_manual_bookings': int(month_manual_sums['bookings'] or 0),
        'month_manual_collected': int(month_manual_sums['paid'] or 0),
        'month_manual_due': int(month_manual_sums['due'] or 0),
        'month_manual_owner_collected': int(month_manual_sums['paid'] or 0),
        'active_owners_this_month': month_bookings.values('slot__ground__owner').distinct().count(),
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'top_grounds': top_grounds,
        'ground_income_ranking': ground_income_ranking,
        'owner_leaderboard': owner_leaderboard,
        'per_ground_data': per_ground_data,
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@login_required
def create_ground_owner(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    if request.method == 'POST':
        form = GroundOwnerCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Ground owner {user.name} created successfully!')
            return redirect('admin_dashboard')
    else:
        form = GroundOwnerCreationForm()

    return render(request, 'accounts/create_ground_owner.html', {'form': form})


@login_required
def edit_ground_owner(request, owner_id):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    owner = get_object_or_404(User, id=owner_id, role='owner')
    if request.method == 'POST':
        form = GroundOwnerEditForm(request.POST, instance=owner)
        if form.is_valid():
            form.save()
            messages.success(request, f'Ground owner {owner.name} updated successfully.')
            return redirect('admin_dashboard')
    else:
        form = GroundOwnerEditForm(instance=owner)

    return render(request, 'accounts/create_ground_owner.html', {
        'form': form,
        'page_title': f'Edit Ground Owner: {owner.name}',
        'page_subtitle': 'Update owner contact details.',
        'submit_label': 'Update Ground Owner',
        'is_edit': True,
    })


@login_required
def delete_ground_owner(request, owner_id):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')
    if request.method != 'POST':
        return redirect('admin_dashboard')

    owner = get_object_or_404(User, id=owner_id, role='owner')
    if Ground.objects.filter(owner=owner).exists():
        messages.error(request, 'Delete this owner only after deleting or reassigning their grounds.')
        return redirect('admin_dashboard')

    owner_name = owner.name
    owner.delete()
    messages.success(request, f'Ground owner {owner_name} deleted successfully.')
    return redirect('admin_dashboard')


@login_required
def toggle_ground_price_drop(request, ground_id):
    if request.user.role != 'admin' or request.method != 'POST':
        messages.error(request, 'Access denied.')
        return redirect('home')

    ground = get_object_or_404(Ground, id=ground_id)
    ground.last_minute_price_drop_enabled = not ground.last_minute_price_drop_enabled
    ground.save(update_fields=['last_minute_price_drop_enabled'])
    state = 'enabled' if ground.last_minute_price_drop_enabled else 'disabled'
    messages.success(request, f'10-minute non-peak price drops are now {state} for {ground.name}.')
    return redirect(request.POST.get('next') or 'admin_dashboard')


@login_required
def toggle_owner_whatsapp_booking_updates(request, owner_id):
    if request.user.role != 'admin' or request.method != 'POST':
        messages.error(request, 'Access denied.')
        return redirect('home')

    owner = get_object_or_404(User, id=owner_id, role='owner')
    owner.whatsapp_booking_updates_enabled = not owner.whatsapp_booking_updates_enabled
    owner.save(update_fields=['whatsapp_booking_updates_enabled'])
    state = 'enabled' if owner.whatsapp_booking_updates_enabled else 'disabled'
    messages.success(request, f'WhatsApp booking updates are now {state} for {owner.name}.')
    return redirect(request.POST.get('next') or 'admin_dashboard')


@login_required
def create_ground(request, owner_id):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    try:
        owner = User.objects.get(id=owner_id, role='owner')
    except User.DoesNotExist:
        messages.error(request, 'Ground owner not found.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        form = GroundCreationForm(request.POST, request.FILES, owner=owner)
        if form.is_valid():
            ground = form.save()
            create_initial_slots_for_ground(
                ground=ground,
                days=14,
                start_date=timezone.localdate(),
            )

            messages.success(request, f'Ground "{ground.name}" created successfully with slots for {owner.name}!')
            return redirect('admin_dashboard')
    else:
        form = GroundCreationForm(owner=owner)

    return render(request, 'accounts/create_ground.html', {
        'form': form,
        'owner': owner,
        'page_title': f'Create Ground for {owner.name}',
        'submit_label': 'Create Ground',
    })


@login_required
def edit_ground(request, ground_id):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    ground = get_object_or_404(Ground.objects.select_related('owner').prefetch_related('groundpricing_set'), id=ground_id)
    if request.method == 'POST':
        form = GroundCreationForm(request.POST, request.FILES, instance=ground, owner=ground.owner)
        if form.is_valid():
            ground = form.save()
            create_initial_slots_for_ground(
                ground=ground,
                days=14,
                start_date=timezone.localdate(),
            )
            messages.success(request, f'Ground "{ground.name}" updated successfully.')
            return redirect(f'{reverse("admin_dashboard")}?owner={ground.owner_id}#all-grounds')
    else:
        form = GroundCreationForm(instance=ground, owner=ground.owner)

    return render(request, 'accounts/create_ground.html', {
        'form': form,
        'owner': ground.owner,
        'ground': ground,
        'page_title': f'Edit Ground: {ground.name}',
        'submit_label': 'Update Ground',
        'is_edit': True,
    })


@login_required
def delete_ground(request, ground_id):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')
    if request.method != 'POST':
        return redirect('admin_dashboard')

    ground = get_object_or_404(Ground.objects.select_related('owner'), id=ground_id)
    owner_id = ground.owner_id
    if Booking.objects.filter(slot__ground=ground).exists():
        messages.error(request, 'This ground has booking history, so it cannot be deleted. Disable it instead.')
        return redirect(f'{reverse("admin_dashboard")}?owner={owner_id}#all-grounds')

    ground_name = ground.name
    ground.delete()
    messages.success(request, f'Ground "{ground_name}" deleted successfully.')
    return redirect(f'{reverse("admin_dashboard")}?owner={owner_id}#all-grounds')


@login_required
def customer_dashboard(request):
    if request.user.role != 'customer':
        messages.error(request, 'Access denied.')
        return redirect('home')
    return redirect('customer_home')


@login_required
def owner_dashboard(request):
    if request.user.role != 'owner':
        messages.error(request, 'Access denied.')
        return redirect('home')

    # Redirect to the existing owner dashboard view
    return redirect('owner_dashboard')


@login_required
def customer_profile(request):
    if request.user.role != 'customer':
        messages.error(request, 'Access denied.')
        return redirect('home')

    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile preferences updated.')
            return redirect('customer_profile')
    else:
        form = CustomerProfileForm(instance=request.user)

    bookings = Booking.objects.filter(user=request.user, status='BOOKED')
    points = request.user.loyalty_points
    rank = (
        User.objects.filter(role='customer')
        .annotate(total_bookings=Count('booking', filter=Q(booking__status='BOOKED')))
        .filter(total_bookings__gt=request.user.booking_count)
        .count() + 1
    )
    return render(request, 'accounts/customer_profile.html', {
        'form': form,
        'active_bookings': bookings.count(),
        'booking_count': request.user.booking_count,
        'loyalty_points': points,
        'free_booking_credits': request.user.free_booking_credits,
        'rank': rank,
    })
