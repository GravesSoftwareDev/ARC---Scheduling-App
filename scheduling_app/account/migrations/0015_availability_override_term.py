import datetime

from django.db import migrations, models


def assign_current_term(apps, schema_editor):
    """Exceptions granted before they were per-term become exceptions for the
    semester the migration runs in (the same term the old global
    availability window was assigned to)."""
    from scheduling.models import term_for_date

    today = datetime.date.today()
    Employee = apps.get_model('account', 'Employee')
    Employee.objects.filter(availability_override_until__isnull=False).update(
        availability_override_term=term_for_date(today),
        availability_override_year=today.year,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0014_birthday_month_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='availability_override_term',
            field=models.CharField(blank=True, default='', max_length=2),
        ),
        migrations.AddField(
            model_name='employee',
            name='availability_override_year',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(assign_current_term, migrations.RunPython.noop),
    ]
