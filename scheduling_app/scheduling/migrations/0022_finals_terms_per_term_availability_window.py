import datetime

from django.db import migrations, models


TERM_CHOICES = [
    ('SP', 'Spring'),
    ('SF', 'Spring Finals'),
    ('SU', 'Summer'),
    ('UF', 'Summer Finals'),
    ('FA', 'Fall'),
    ('FF', 'Fall Finals'),
]


def assign_current_term(apps, schema_editor):
    """The old single, global availability window becomes the window for the
    semester the migration runs in; every other term starts closed."""
    from scheduling.models import term_for_date

    today = datetime.date.today()
    AvailabilityWindow = apps.get_model('scheduling', 'AvailabilityWindow')
    AvailabilityWindow.objects.update(term=term_for_date(today), year=today.year)


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0021_weeklyavailability_term_year'),
    ]

    operations = [
        migrations.AlterField(
            model_name='weeklyavailability',
            name='term',
            field=models.CharField(choices=TERM_CHOICES, max_length=2),
        ),
        migrations.AlterField(
            model_name='weeklyschedule',
            name='term',
            field=models.CharField(choices=TERM_CHOICES, max_length=2),
        ),
        migrations.AddField(
            model_name='availabilitywindow',
            name='term',
            field=models.CharField(choices=TERM_CHOICES, default='FA', max_length=2),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='availabilitywindow',
            name='year',
            field=models.PositiveSmallIntegerField(default=2026),
            preserve_default=False,
        ),
        migrations.RunPython(assign_current_term, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='availabilitywindow',
            name='is_open',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterUniqueTogether(
            name='availabilitywindow',
            unique_together={('term', 'year')},
        ),
        migrations.AlterModelOptions(
            name='availabilitywindow',
            options={'verbose_name_plural': 'Availability Windows'},
        ),
    ]
