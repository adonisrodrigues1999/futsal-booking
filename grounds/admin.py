from django.contrib import admin

# Register your models here.
from .models import Ground, Tournament
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
