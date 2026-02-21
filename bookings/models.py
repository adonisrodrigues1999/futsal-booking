from django.db import models
from django.conf import settings
import uuid
from grounds.models import Ground
from django.utils.timezone import now

class Slot(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        unique_together = ('ground', 'date', 'start_time')

    def __str__(self):
        return f"{self.ground.name} - {self.date} {self.start_time}-{self.end_time}"


class Booking(models.Model):
    SOURCE = (('ONLINE','Online'), ('MANUAL','Manual'))
    STATUS = (('BOOKED','Booked'), ('CANCELLED','Cancelled'))
    PAYMENT_MODE = (('FULL', 'Full Payment'), ('PARTIAL_99', 'Advance ₹99'))
    PAYMENT_STATUS = (
        ('PENDING', 'Pending'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    customer_name = models.CharField(max_length=100)
    customer_phone = models.CharField(max_length=15)

    duration_hours = models.PositiveIntegerField(default=1)
    total_amount = models.PositiveIntegerField()
    platform_fee = models.PositiveIntegerField(default=3)
    owner_payout = models.PositiveIntegerField()

    booking_source = models.CharField(max_length=10, choices=SOURCE, default='ONLINE')
    status = models.CharField(max_length=10, choices=STATUS, default='BOOKED')
    payment_mode = models.CharField(max_length=12, choices=PAYMENT_MODE, default='FULL')
    payment_status = models.CharField(max_length=16, choices=PAYMENT_STATUS, default='PAID')
    paid_amount = models.PositiveIntegerField(default=0)
    due_amount = models.PositiveIntegerField(default=0)
    payment_paid_at = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    def __str__(self):
        return f"Booking {self.id} - {self.customer_name}"


class BookingActivityLog(models.Model):
    ACTIONS = (('CREATED','Created'), ('CANCELLED','Cancelled'))

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTIONS)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    role = models.CharField(max_length=10)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} by {self.performed_by} on {self.booking}"



class CommissionLedger(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE)

    commission_amount = models.DecimalField(max_digits=6, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)


class GroundInvoice(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    period_start = models.DateField()
    period_end = models.DateField()
    bookings_count = models.PositiveIntegerField()
    charge_per_booking = models.DecimalField(max_digits=8, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start', '-ground']

    def __str__(self):
        return f"Invoice {self.ground.name} {self.period_start} - {self.period_end}"


class EmailVerification(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('BOOKED', 'Booked'),
        ('MANUAL_BOOKING', 'Manual Booking'),
        ('CUSTOMER_CANCELLED', 'Customer Cancelled'),
        ('OWNER_CANCELLED', 'Owner Cancelled'),
        ('ADMIN_ACTION', 'Admin Action'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True)
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE, null=True, blank=True)

    meta = models.JSONField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} | {self.user} | {self.timestamp}"
