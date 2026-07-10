from django.contrib import admin
from .models import (
    CommissionLedger,
    Slot,
    Booking,
    BookingActivityLog,
    BookingAttendance,
    ActivityLog,
    OwnerExpense,
    RewardTransaction,
    AlertSubscription,
    AlertDispatchLog,
)
from .models import GroundInvoice
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


@admin.register(BookingAttendance)
class BookingAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        'booking',
        'status',
        'marked_by',
        'marked_at',
        'updated_at',
    )
    list_filter = ('status', 'marked_at')
    search_fields = ('booking__id', 'booking__customer_name', 'booking__customer_phone')
    autocomplete_fields = ('booking', 'marked_by')

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


@admin.register(GroundInvoice)
class GroundInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'ground',
        'period_start',
        'period_end',
        'bookings_count',
        'charge_per_booking',
        'total_amount',
        'is_paid',
        'created_at'
    )
    list_filter = ('is_paid', 'ground')
    search_fields = ('ground__name',)


@admin.register(OwnerExpense)
class OwnerExpenseAdmin(admin.ModelAdmin):
    list_display = (
        'owner',
        'ground',
        'title',
        'category',
        'amount',
        'spent_on',
    )
    list_filter = ('category', 'spent_on', 'ground')
    search_fields = ('owner__name', 'title', 'note')


@admin.register(RewardTransaction)
class RewardTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'reason', 'points', 'booking', 'created_at')
    list_filter = ('reason',)
    search_fields = ('user__name', 'user__email', 'notes')


@admin.register(AlertSubscription)
class AlertSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ground', 'notify_price_drops', 'notify_last_minute', 'notify_nearby_tournaments', 'email_enabled', 'push_enabled')
    list_filter = ('email_enabled', 'push_enabled', 'notify_price_drops', 'notify_last_minute', 'notify_nearby_tournaments')


@admin.register(AlertDispatchLog)
class AlertDispatchLogAdmin(admin.ModelAdmin):
    list_display = ('reason', 'ground', 'tournament', 'alert_date', 'created_at')
    list_filter = ('reason', 'alert_date')
