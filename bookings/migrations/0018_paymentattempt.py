from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [('bookings', '0017_onlinesettlement_onlinesettlementlineitem_and_more')]

    operations = [
        migrations.CreateModel(
            name='PaymentAttempt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('payment_mode', models.CharField(choices=[('FULL', 'Full Payment'), ('PARTIAL_99', 'Advance ₹99'), ('FREE_REWARD', 'Free Booking Credit')], max_length=12)),
                ('total_amount', models.PositiveIntegerField()),
                ('pay_now_amount', models.PositiveIntegerField()),
                ('due_amount', models.PositiveIntegerField()),
                ('razorpay_order_id', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending payment'), ('CAPTURED', 'Payment received'), ('BOOKED', 'Booking confirmed'), ('ACTION_REQUIRED', 'Needs support'), ('FAILED', 'Failed')], default='PENDING', max_length=20)),
                ('failure_reason', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_attempt', to='bookings.booking')),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bookings.slot')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(model_name='paymentattempt', index=models.Index(fields=['user', 'status', 'created_at'], name='bookings_pa_user_id_1caae4_idx')),
        migrations.AddIndex(model_name='paymentattempt', index=models.Index(fields=['status', 'created_at'], name='bookings_pa_status_d31d06_idx')),
    ]
