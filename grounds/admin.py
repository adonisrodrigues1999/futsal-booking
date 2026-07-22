from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

# Register your models here.
from .models import Ground, Tournament, TournamentRegistration, GroundReview
from bookings.slot_generation import ensure_slots_for_ground_date


@admin.action(description='Mark selected grounds as available')
def mark_ground_available(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description='Mark selected grounds as temporarily unavailable')
def mark_ground_unavailable(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.action(description='Generate slots for next 3 months')
def generate_slots_for_3_months(modeladmin, request, queryset):
    """Generate slots for the next 3 months for selected grounds."""
    start_date = timezone.localdate()
    end_date = start_date + timedelta(days=90)  # 3 months approximately
    
    total_slots_created = 0
    for ground in queryset:
        current_date = start_date
        while current_date <= end_date:
            ensure_slots_for_ground_date(ground=ground, slot_date=current_date)
            current_date += timedelta(days=1)
    
    modeladmin.message_user(request, f"Slots generated for {queryset.count()} ground(s) for the next 3 months.")


@admin.register(Ground)
class GroundAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'location',
        'owner',
        'day_price',
        'night_price',
        'is_active',
        'last_minute_price_drop_enabled',
        'created_at',
    )
    search_fields = ('name', 'location')
    list_filter = ('is_active', 'last_minute_price_drop_enabled')
    actions = (mark_ground_available, mark_ground_unavailable, generate_slots_for_3_months)
    autocomplete_fields = ('owner',)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'ground',
        'start_date',
        'end_date',
        'status',
        'is_published',
    )
    list_filter = ('status', 'is_published', 'start_date', 'ground')
    search_fields = ('title', 'ground__name', 'ground__location')
    autocomplete_fields = ('ground',)


@admin.register(TournamentRegistration)
class TournamentRegistrationAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'team_name', 'category_name', 'contact_phone', 'status', 'created_at')
    search_fields = ('team_name', 'contact_phone', 'tournament__title')
    list_filter = ('status', 'tournament')


@admin.register(GroundReview)
class GroundReviewAdmin(admin.ModelAdmin):
    list_display = ('ground', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'ground')
    search_fields = ('ground__name', 'user__name', 'comment')
