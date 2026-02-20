from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
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

            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('login')
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
