from django.db import models
from django.conf import settings
import uuid

class Ground(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    # optional image path or URL (can be a relative static path or stored media URL)
    image = models.CharField(max_length=300, blank=True, null=True)
    # optional coordinates (latitude/longitude) for map previews
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'owner'}
    )

    day_price = models.PositiveIntegerField()
    night_price = models.PositiveIntegerField()

    opening_time = models.TimeField()
    closing_time = models.TimeField()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GroundPricing(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()
    price_per_hour = models.PositiveIntegerField()


class Tournament(models.Model):
    STATUS_CHOICES = (
        ('UPCOMING', 'Upcoming'),
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )

    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name='tournaments')
    image = models.ImageField(upload_to='tournaments/', blank=True, null=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    registration_deadline = models.DateField(null=True, blank=True)
    entry_fee = models.PositiveIntegerField(default=0)
    prize_details = models.CharField(max_length=250, blank=True)
    max_teams = models.PositiveIntegerField(null=True, blank=True)
    contact_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    category_fees = models.JSONField(default=list, blank=True)
    rules = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='UPCOMING')
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_date', 'start_time', 'title']
        indexes = [
            models.Index(fields=['is_published', 'status', 'start_date']),
            models.Index(fields=['ground', 'start_date']),
        ]

    def __str__(self):
        return f"{self.title} - {self.ground.name}"


class TournamentRegistration(models.Model):
    STATUS_CHOICES = (
        ('REGISTERED', 'Registered'),
        ('CANCELLED', 'Cancelled'),
    )

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='registrations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='tournament_registrations')
    team_name = models.CharField(max_length=120)
    captain_name = models.CharField(max_length=100, blank=True)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField(blank=True)
    category_name = models.CharField(max_length=120)
    fee_amount = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='REGISTERED')
    notes = models.TextField(blank=True)
    referral_bonus_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tournament', 'contact_phone', 'category_name')
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['tournament', 'created_at']),
        ]

    def __str__(self):
        return f"{self.team_name} | {self.tournament.title}"


class GroundReview(models.Model):
    ground = models.ForeignKey(Ground, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    rating = models.PositiveSmallIntegerField(default=5)
    headline = models.CharField(max_length=120, blank=True)
    comment = models.TextField()
    photo = models.ImageField(upload_to='ground-reviews/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ground', '-created_at']),
        ]

    def __str__(self):
        return f"{self.ground.name} review by {self.user or 'Guest'}"
