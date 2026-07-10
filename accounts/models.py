from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
import secrets
from .managers import UserManager

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('owner', 'Ground Owner'),
        ('customer', 'Customer'),
    )

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100)

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    email_verified = models.BooleanField(default=False)
    referral_code = models.CharField(max_length=12, unique=True, null=True, blank=True, editable=False)
    referred_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referrals',
    )
    booking_count = models.PositiveIntegerField(default=0)
    loyalty_points = models.PositiveIntegerField(default=0)
    free_booking_credits = models.PositiveIntegerField(default=0)

    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'name']

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.referral_code:
            code = secrets.token_hex(3).upper()
            self.referral_code = f'FB{code}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.email})"
