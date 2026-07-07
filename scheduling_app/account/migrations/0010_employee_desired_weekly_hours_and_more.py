from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0009_data_migrate_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='desired_weekly_hours',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='employee',
            name='wants_lunch_break',
            field=models.BooleanField(default=False),
        ),
    ]
