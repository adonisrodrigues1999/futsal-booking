from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0004_user_whatsapp_booking_updates_enabled')]

    operations = [
        migrations.CreateModel(
            name='CustomerLoginOTP',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_hash', models.CharField(max_length=128)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('requested_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('phone_number', models.CharField(db_index=True, max_length=10)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='login_otps', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(model_name='customerloginotp', index=models.Index(fields=['phone_number', 'created_at'], name='accounts_cu_phone_n_0f1e74_idx')),
        migrations.AddIndex(model_name='customerloginotp', index=models.Index(fields=['expires_at'], name='accounts_cu_expires_19fecc_idx')),
    ]
