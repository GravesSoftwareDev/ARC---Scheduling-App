import datetime

from django.db import migrations, models


def assign_current_term(apps, schema_editor):
    """Availability saved before semesters existed becomes the availability
    for the semester the migration runs in."""
    from scheduling.models import term_for_date

    today = datetime.date.today()
    WeeklyAvailability = apps.get_model('scheduling', 'WeeklyAvailability')
    WeeklyAvailability.objects.update(term=term_for_date(today), year=today.year)


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0020_weeklyschedule_term_year'),
    ]

    operations = [
        migrations.AddField(
            model_name='weeklyavailability',
            name='term',
            field=models.CharField(choices=[('SP', 'Spring'), ('SU', 'Summer'), ('FA', 'Fall')], default='FA', max_length=2),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='weeklyavailability',
            name='year',
            field=models.PositiveSmallIntegerField(default=2026),
            preserve_default=False,
        ),
        migrations.RunPython(assign_current_term, migrations.RunPython.noop),
    ]
