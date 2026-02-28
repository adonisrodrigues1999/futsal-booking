from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0009_ownerexpense'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('PARTIALLY_PAID', 'Partially Paid'),
                    ('PAID', 'Paid'),
                    ('PAID_AT_GROUND', 'Paid at Ground'),
                    ('FAILED', 'Failed'),
                ],
                default='PAID',
                max_length=16,
            ),
        ),
    ]
