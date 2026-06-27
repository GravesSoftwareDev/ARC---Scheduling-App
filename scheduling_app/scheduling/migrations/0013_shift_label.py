from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0012_employee_shift_label'),
    ]

    operations = [
        migrations.DeleteModel(name='EmployeeShiftLabel'),
        migrations.CreateModel(
            name='ShiftLabel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(max_length=7)),
                ('schedule', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='shift_labels',
                    to='scheduling.schedule',
                )),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('schedule', 'name')},
            },
        ),
    ]
