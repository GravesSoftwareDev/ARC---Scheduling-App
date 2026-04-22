import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('account', '0004_employee_birthdate'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE account_weeklyavailability RENAME TO scheduling_weeklyavailability",
                    reverse_sql="ALTER TABLE scheduling_weeklyavailability RENAME TO account_weeklyavailability",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE account_operatinghours RENAME TO scheduling_operatinghours",
                    reverse_sql="ALTER TABLE scheduling_operatinghours RENAME TO account_operatinghours",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='WeeklyAvailability',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('day_of_week', models.CharField(choices=[('MON', 'Monday'), ('TUE', 'Tuesday'), ('WED', 'Wednesday'), ('THU', 'Thursday'), ('FRI', 'Friday')], max_length=3)),
                        ('start_time', models.TimeField()),
                        ('end_time', models.TimeField()),
                        ('availability_type', models.CharField(choices=[('AVAILABLE', 'Available'), ('PREFERRED', 'Preferred')], default='AVAILABLE', max_length=10)),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='weekly_availability', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'verbose_name_plural': 'Weekly Availabilities',
                        'ordering': ['day_of_week', 'start_time'],
                    },
                ),
                migrations.CreateModel(
                    name='OperatingHours',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('day_of_week', models.CharField(choices=[('MON', 'Monday'), ('TUE', 'Tuesday'), ('WED', 'Wednesday'), ('THU', 'Thursday'), ('FRI', 'Friday')], max_length=3, unique=True)),
                        ('start_time', models.TimeField()),
                        ('end_time', models.TimeField()),
                    ],
                    options={
                        'verbose_name_plural': 'Operating Hours',
                        'ordering': ['day_of_week'],
                    },
                ),
            ],
        ),
    ]
