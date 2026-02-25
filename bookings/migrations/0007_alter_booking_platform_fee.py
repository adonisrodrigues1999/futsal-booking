from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0006_booking_payment_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='platform_fee',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
