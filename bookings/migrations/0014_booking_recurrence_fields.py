from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0013_alter_booking_payment_mode_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='recurrence_group',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='recurrence_position',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
