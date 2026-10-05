"""Replace Employee.birthdate (full date) with birth_month + birth_day.

Runs in three steps so no existing birthday is lost:
  1. add the new month/day columns,
  2. copy month/day out of every existing birthdate,
  3. drop the old birthdate column (this is where the year is discarded).

Reversible: rolling back rebuilds birthdate using the placeholder year 2000
(a leap year, so Feb 29 survives). The original years are not recoverable.
"""

import datetime

import django.core.validators
from django.db import migrations, models

PLACEHOLDER_YEAR = 2000


def copy_birthdate_to_month_day(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    for emp in Employee.objects.exclude(birthdate__isnull=True).only('pk', 'birthdate'):
        Employee.objects.filter(pk=emp.pk).update(
            birth_month=emp.birthdate.month,
            birth_day=emp.birthdate.day,
        )


def copy_month_day_to_birthdate(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    qs = Employee.objects.exclude(birth_month__isnull=True).exclude(birth_day__isnull=True)
    for emp in qs.only('pk', 'birth_month', 'birth_day'):
        Employee.objects.filter(pk=emp.pk).update(
            birthdate=datetime.date(PLACEHOLDER_YEAR, emp.birth_month, emp.birth_day),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0013_securitysettings_alter_employee_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='birth_month',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                choices=[(1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
                         (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
                         (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')],
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='birth_day',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True,
                validators=[django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(31)],
            ),
        ),
        migrations.RunPython(copy_birthdate_to_month_day, copy_month_day_to_birthdate),
        migrations.RemoveField(
            model_name='employee',
            name='birthdate',
        ),
    ]
