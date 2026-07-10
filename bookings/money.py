from django.db.models import Case, ExpressionWrapper, F, IntegerField, Value, When


def online_collected_amount_expression():
    return Case(
        When(
            booking_source='ONLINE',
            payment_mode='PARTIAL_99',
            paid_amount__gt=0,
            then=Value(99),
        ),
        When(booking_source='ONLINE', then=F('paid_amount')),
        default=Value(0),
        output_field=IntegerField(),
    )


def ground_collected_amount_expression():
    online_balance_collected_at_ground = ExpressionWrapper(
        F('total_amount') - Value(99),
        output_field=IntegerField(),
    )
    return Case(
        When(booking_source='MANUAL', then=F('paid_amount')),
        When(
            booking_source='ONLINE',
            payment_mode='PARTIAL_99',
            payment_status='PAID_AT_GROUND',
            then=online_balance_collected_at_ground,
        ),
        default=Value(0),
        output_field=IntegerField(),
    )
