from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0008_alter_activitylog_action'),
    ]

    operations = [
        migrations.CreateModel(
            name='OwnerExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120)),
                ('category', models.CharField(choices=[('RENT', 'Ground Rent'), ('SALARY', 'Staff Salary'), ('EQUIPMENT', 'Equipment'), ('MAINTENANCE', 'Maintenance'), ('UTILITIES', 'Utilities'), ('MARKETING', 'Marketing'), ('OTHER', 'Other')], default='OTHER', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('spent_on', models.DateField(default=django.utils.timezone.now)),
                ('note', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ground', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='grounds.ground')),
                ('owner', models.ForeignKey(limit_choices_to={'role': 'owner'}, on_delete=django.db.models.deletion.CASCADE, to='accounts.user')),
            ],
            options={
                'ordering': ['-spent_on', '-created_at'],
            },
        ),
    ]
