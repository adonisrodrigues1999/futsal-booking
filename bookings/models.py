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
        indexes = [
            models.Index(fields=['ground', 'date']),
        ]

    def __str__(self):
        return f"{self.ground.name} - {self.date} {self.start_time}-{self.end_time}"


class Booking(models.Model):
    SOURCE = (('ONLINE','Online'), ('MANUAL','Manual'))
    STATUS = (('BOOKED','Booked'), ('CANCELLED','Cancelled'))
    PAYMENT_MODE = (('FULL', 'Full Payment'), ('PARTIAL_99', 'Advance ₹99'), ('FREE_REWARD', 'Free Booking Credit'))
    PAYMENT_STATUS = (
        ('PENDING', 'Pending'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('PAID_AT_GROUND', 'Paid at Ground'),
        ('FAILED', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    customer_name = models.CharField(max_length=100)
    customer_phone = models.CharField(max_length=15)

    duration_hours = models.PositiveIntegerField(default=1)
    total_amount = models.PositiveIntegerField()
    platform_fee = models.PositiveIntegerField(default=0)
    owner_payout = models.PositiveIntegerField()

    booking_source = models.CharField(max_length=10, choices=SOURCE, default='ONLINE')
    status = models.CharField(max_length=10, choices=STATUS, default='BOOKED')
    payment_mode = models.CharField(max_length=12, choices=PAYMENT_MODE, default='FULL')
    payment_status = models.CharField(max_length=16, choices=PAYMENT_STATUS, default='PAID')
    paid_amount = models.PositiveIntegerField(default=0)
    due_amount = models.PositiveIntegerField(default=0)
    reward_discount_amount = models.PositiveIntegerField(default=0)
    reward_points_earned = models.PositiveIntegerField(default=0)
    loyalty_reward_redeemed = models.BooleanField(default=False)
    payment_paid_at = models.DateTimeField(null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=200, blank=True, null=True)
    recurrence_group = models.UUIDField(null=True, blank=True, db_index=True)
    recurrence_position = models.PositiveIntegerField(default=0)
    invoiced_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['status', 'slot']),
            models.Index(fields=['booking_source', 'created_at']),
        ]

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


class BookingAttendance(models.Model):
    STATUS_CHOICES = (
        ('SHOWED_UP', 'Showed Up'),
        ('NO_SHOW', 'No Show'),
        ('UNMARKED', 'Unmarked'),
    )

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='attendance')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='UNMARKED')
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    marked_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.booking_id} - {self.get_status_display()}"



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
    settled_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='settled_ground_invoices',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start', '-ground']
        constraints = [
            models.UniqueConstraint(
                fields=['ground', 'period_start', 'period_end'],
                name='unique_ground_invoice_period',
            ),
        ]

    def __str__(self):
        return f"Invoice {self.ground.name} {self.period_start} - {self.period_end}"


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(GroundInvoice, on_delete=models.CASCADE, related_name='line_items')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    charge_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('invoice', 'booking')
        ordering = ['booking__slot__date', 'booking__slot__start_time']

    def __str__(self):
        return f"Line {self.invoice_id} - Booking {self.booking_id}"


class SettlementRefund(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='settlements')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='processed_settlements'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Settlement {self.id} - ₹{self.amount} ({self.status})"


class EmailVerification(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class OwnerExpense(models.Model):
    CATEGORY_CHOICES = (
        ('RENT', 'Ground Rent'),
        ('SALARY', 'Staff Salary'),
        ('EQUIPMENT', 'Equipment'),
        ('MAINTENANCE', 'Maintenance'),
        ('UTILITIES', 'Utilities'),
        ('MARKETING', 'Marketing'),
        ('OTHER', 'Other'),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'owner'}
    )
    ground = models.ForeignKey(Ground, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    spent_on = models.DateField(default=now)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-spent_on', '-created_at']
        indexes = [
            models.Index(fields=['owner', 'spent_on']),
        ]

    def __str__(self):
        return f"{self.owner} | {self.category} | {self.amount}"


class RewardTransaction(models.Model):
    REASON_CHOICES = (
        ('BOOKING', 'Booking'),
        ('FIRST_BOOKING_REFERRAL', 'First Booking Referral'),
        ('FIRST_TOURNAMENT_REGISTRATION', 'First Tournament Registration'),
        ('LOYALTY_REDEMPTION', 'Loyalty Redemption'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reward_transactions')
    reason = models.CharField(max_length=40, choices=REASON_CHOICES)
    points = models.PositiveIntegerField()
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.CASCADE)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user} | {self.reason} | {self.points}"


class AlertSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alert_subscriptions')
    ground = models.ForeignKey(Ground, null=True, blank=True, on_delete=models.CASCADE, related_name='alert_subscriptions')
    notify_price_drops = models.BooleanField(default=True)
    notify_last_minute = models.BooleanField(default=True)
    notify_nearby_tournaments = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'ground')
        indexes = [
            models.Index(fields=['user', 'ground']),
        ]

    def __str__(self):
        scope = self.ground.name if self.ground else 'Global'
        return f"{self.user} | {scope}"


class AlertDispatchLog(models.Model):
    REASON_CHOICES = (
        ('PRICE_DROP', 'Price Drop'),
        ('LAST_MINUTE_OPENING', 'Last Minute Opening'),
        ('TOURNAMENT_PUBLISHED', 'Tournament Published'),
    )

    ground = models.ForeignKey(Ground, null=True, blank=True, on_delete=models.CASCADE)
    tournament = models.ForeignKey('grounds.Tournament', null=True, blank=True, on_delete=models.CASCADE)
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    alert_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('ground', 'tournament', 'reason', 'alert_date')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ground', 'alert_date']),
            models.Index(fields=['tournament', 'alert_date']),
        ]

    def __str__(self):
        return f"{self.reason} | {self.ground or self.tournament}"


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('BOOKED', 'Booked'),
        ('MANUAL_BOOKING', 'Manual Booking'),
        ('CUSTOMER_CANCELLED', 'Customer Cancelled'),
        ('OWNER_CANCELLED', 'Owner Cancelled'),
        ('CUSTOMER_RESCHEDULED', 'Customer Rescheduled'),
        ('OWNER_RESCHEDULED', 'Owner Rescheduled'),
        ('OWNER_MARKED_PAID', 'Owner Marked Paid'),
        ('OWNER_MARKED_ATTENDANCE', 'Owner Marked Attendance'),
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

    class Meta:
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['booking', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.action} | {self.user} | {self.timestamp}"
