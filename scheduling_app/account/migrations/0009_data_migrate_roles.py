from django.db import migrations


def migrate_roles_forward(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    # Former admins become Assistant II with admin flag
    Employee.objects.filter(role='ADMIN').update(role='ASSISTANT_II', is_admin=True)
    # Former ARC Assistants become Assistant I
    Employee.objects.filter(role='ARC_ASSISTANT').update(role='ASSISTANT_I')


def migrate_roles_backward(apps, schema_editor):
    Employee = apps.get_model('account', 'Employee')
    Employee.objects.filter(role='ASSISTANT_II', is_admin=True).update(role='ADMIN', is_admin=False)
    Employee.objects.filter(role='ASSISTANT_I').update(role='ARC_ASSISTANT')


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0008_role_overhaul_and_is_admin'),
    ]

    operations = [
        migrations.RunPython(migrate_roles_forward, migrate_roles_backward),
    ]
