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
