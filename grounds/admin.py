from django.contrib import admin

# Register your models here.
from .models import Ground
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