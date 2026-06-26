from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0010_schedule_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleentry',
            name='custom_label',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
