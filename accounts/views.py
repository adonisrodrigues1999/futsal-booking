from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.forms import SetPasswordForm
from django import forms
from .models import User
from bookings.models import EmailVerification
from bookings.slot_generation import create_initial_slots_for_ground
from .forms import UserRegistrationForm, UserLoginForm, GroundOwnerCreationForm, GroundCreationForm
from grounds.models import Ground


def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email_verified = False
            user.save()

            # Create email verification token
            verification = EmailVerification.objects.create(user=user)

            # Send verification email
            verification_url = request.build_absolute_uri(
                reverse('verify_email', args=[verification.token])
            )
            send_mail(
                'Verify your email - FootBook',
                f'Click the link to verify your email: {verification_url}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            # Instead of redirecting immediately, render the register page
            # and set a flag so the frontend shows a prominent popup and
            # then redirects the user to the login page.
            form = UserRegistrationForm()
            return render(request, 'accounts/register.html', {
                'form': form,
                'show_verification_popup': True,
                'verification_message': 'Registration successful! Please check your email to verify your account.'
            })
    else:
        form = UserRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('email')
            phone = form.cleaned_data.get('phone')
            password = form.cleaned_data['password']

            # Determine which identifier to use
            identifier = email if email else phone

            # Try to authenticate with email first, then phone
            user = None
            try:
                if email:
                    user_obj = User.objects.get(email=email)
                    user = authenticate(request, username=email, password=password)
                elif phone:
                    user_obj = User.objects.get(phone_number=phone)
                    user = authenticate(request, username=user_obj.email, password=password)
            except User.DoesNotExist:
                pass

            if user is not None:
                if user.email_verified:
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.name}!')

                    # Redirect based on user role
                    if user.role == 'admin':
                        return redirect('admin_dashboard')
                    elif user.role == 'owner':
                        return redirect('owner_dashboard')
                    else:  # customer
                        return redirect('customer_dashboard')
                else:
                    messages.error(request, 'Please verify your email before logging in.')
                    return redirect('login')
            else:
                messages.error(request, 'Invalid credentials.')
    else:
        form = UserLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


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
            messages.success(request, 'Email verified successfully! You can now log in.')
        else:
            messages.info(request, 'Email already verified.')
    except EmailVerification.DoesNotExist:
        messages.error(request, 'Invalid verification link.')

    return redirect('login')


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField()


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

    return render(request, 'accounts/password_reset_confirm.html', {'form': form})


def password_reset_complete(request):
    return render(request, 'accounts/password_reset_complete.html')


@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied.')
        return redirect('home')

    ground_owners = User.objects.filter(role='owner')
    grounds = Ground.objects.all()
    customers = User.objects.filter(role='customer')

    context = {
        'ground_owners': ground_owners,
        'grounds': grounds,
        'customers': customers,
        'total_owners': ground_owners.count(),
        'total_grounds': grounds.count(),
        'total_customers': customers.count(),
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
        form = GroundCreationForm(request.POST, owner=owner)
        if form.is_valid():
            ground = form.save()
            create_initial_slots_for_ground(
                ground=ground,
                days=14,
                start_date=timezone.localdate(),
                slot_config=form.cleaned_data,
            )

            messages.success(request, f'Ground "{ground.name}" created successfully with slots for {owner.name}!')
            return redirect('admin_dashboard')
    else:
        form = GroundCreationForm(owner=owner)

    return render(request, 'accounts/create_ground.html', {
        'form': form,
        'owner': owner
    })


@login_required
def customer_dashboard(request):
    if request.user.role != 'customer':
        messages.error(request, 'Access denied.')
        return redirect('home')

    # Redirect to the existing customer home view
    return redirect('customer_home')


@login_required
def owner_dashboard(request):
    if request.user.role != 'owner':
        messages.error(request, 'Access denied.')
        return redirect('home')

    # Redirect to the existing owner dashboard view
    return redirect('owner_dashboard')
