from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0004_employee_birthdate'),
        ('scheduling', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='WeeklyAvailability'),
                migrations.DeleteModel(name='OperatingHours'),
            ],
        ),
    ]
