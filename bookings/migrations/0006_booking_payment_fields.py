from django.db import migrations, models


def populate_existing_booking_payment_fields(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.all().iterator():
        total = booking.total_amount or 0
        if booking.booking_source == 'MANUAL':
            booking.payment_mode = 'FULL'
            booking.payment_status = 'PAID'
            booking.paid_amount = total
            booking.due_amount = 0
        else:
            booking.payment_mode = 'FULL'
            booking.payment_status = 'PAID' if booking.status == 'BOOKED' else 'FAILED'
            booking.paid_amount = total if booking.status == 'BOOKED' else 0
            booking.due_amount = 0 if booking.status == 'BOOKED' else total
        booking.save(update_fields=['payment_mode', 'payment_status', 'paid_amount', 'due_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0005_groundinvoice'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='due_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='booking',
            name='paid_amount',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='booking',
            name='payment_mode',
            field=models.CharField(choices=[('FULL', 'Full Payment'), ('PARTIAL_99', 'Advance ₹99')], default='FULL', max_length=12),
        ),
        migrations.AddField(
            model_name='booking',
            name='payment_paid_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='payment_status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('PARTIALLY_PAID', 'Partially Paid'), ('PAID', 'Paid'), ('FAILED', 'Failed')], default='PAID', max_length=16),
        ),
        migrations.AddField(
            model_name='booking',
            name='razorpay_order_id',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='razorpay_payment_id',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='razorpay_signature',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.RunPython(populate_existing_booking_payment_fields, migrations.RunPython.noop),
    ]
