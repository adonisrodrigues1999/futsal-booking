from django.contrib import admin

# Register your models here.
from .models import Ground, Tournament, TournamentRegistration, GroundReview


@admin.action(description='Mark selected grounds as available')
def mark_ground_available(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description='Mark selected grounds as temporarily unavailable')
def mark_ground_unavailable(modeladmin, request, queryset):
    queryset.update(is_active=False)


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
        'created_at',
    )
    search_fields = ('name', 'location')
    list_filter = ('is_active',)
    actions = (mark_ground_available, mark_ground_unavailable)
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
