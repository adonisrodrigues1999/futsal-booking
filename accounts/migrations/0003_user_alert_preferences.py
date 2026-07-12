from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_booking_count_user_free_booking_credits_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_alerts',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_last_minute',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_nearby_tournaments',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='notify_price_drops',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='user',
            name='push_alerts',
            field=models.BooleanField(default=False),
        ),
    ]
