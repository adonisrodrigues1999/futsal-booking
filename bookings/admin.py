from django.contrib import admin
from .models import (
    CommissionLedger,
    Slot,
    Booking,
    BookingActivityLog,
    ActivityLog
)
from grounds.models import Ground




@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = (
        'ground',
        'start_time',
        'end_time',
        'is_booked'
    )

    search_fields = (
        'ground__name',
        'ground__location',
    )

    list_filter = ('ground', 'is_booked')
    ordering = ('start_time',)


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'customer_name',
        'customer_phone',
        'slot',
        'total_amount',
        'status',
        'booking_source',
    )

    search_fields = (
        'customer_name',
        'customer_phone',
        'slot__ground__name',
    )

    list_filter = ('booking_source', 'status', 'slot__ground')

    date_hierarchy = 'created_at'
    
    
@admin.register(BookingActivityLog)
class BookingActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp',
        'performed_by',
        'action',
        'booking',
    )

    search_fields = (
        'performed_by__email',
        'performed_by__phone_number',
        'booking__id',
    )

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp',
        'user',
        'action',
        'slot'
    )

    search_fields = (
        'user__email',
        'user__username',
        'slot__ground__name',
    )

    list_filter = (
        'action',
        'slot__ground',
    )

    readonly_fields = ('timestamp',)





@admin.register(CommissionLedger)
class CommissionLedgerAdmin(admin.ModelAdmin):
    list_display = (
        'ground',
        'booking',
        'commission_amount',
        'is_paid',
        'created_at'
    )

    search_fields = (
        'ground__name',
        'booking__id',
    )

    list_filter = ('is_paid', 'ground')