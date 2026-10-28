import datetime

from django.db import migrations, models


def assign_current_term(apps, schema_editor):
    """Default weeks saved before semesters existed become the default for
    the semester the migration runs in."""
    from scheduling.models import term_for_date

    today = datetime.date.today()
    WeeklySchedule = apps.get_model('scheduling', 'WeeklySchedule')
    WeeklySchedule.objects.update(term=term_for_date(today), year=today.year)


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0019_employee_color'),
    ]

    operations = [
        migrations.AddField(
            model_name='weeklyschedule',
            name='term',
            field=models.CharField(choices=[('SP', 'Spring'), ('SU', 'Summer'), ('FA', 'Fall')], default='FA', max_length=2),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='weeklyschedule',
            name='year',
            field=models.PositiveSmallIntegerField(default=2026),
            preserve_default=False,
        ),
        migrations.RunPython(assign_current_term, migrations.RunPython.noop),
    ]
