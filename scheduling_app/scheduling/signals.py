from django.db.models.signals import post_save
from django.dispatch import receiver


def _role_keyword(role):
    """Return the schedule name keyword that auto-matches a given role, or None."""
    if role == 'ASSISTANT_I':
        return 'assistant i'
    if role == 'ASSISTANT_II':
        return 'assistant ii'
    return None


def _schedules_for_role(Schedule, role):
    """Return schedules whose name matches the given role keyword."""
    keyword = _role_keyword(role)
    if not keyword:
        return Schedule.objects.none()
    # Case-insensitive: name contains the keyword
    # "Assistant II" must be checked before "Assistant I" to avoid false matches,
    # so we match exactly on the keyword string (which differs by the trailing 'I' or 'II').
    return Schedule.objects.filter(name__icontains=keyword).exclude(
        # Exclude "Assistant II" schedules when looking for "Assistant I" matches
        **({'name__icontains': 'assistant ii'} if role == 'ASSISTANT_I' else {})
    )


@receiver(post_save, sender='account.Employee')
def sync_employee_to_schedules(sender, instance, created, **kwargs):
    from scheduling.models import Schedule
    keyword = _role_keyword(instance.role)
    if not keyword:
        return
    matching = _schedules_for_role(Schedule, instance.role)
    for schedule in matching:
        schedule.members.add(instance)


@receiver(post_save, sender='scheduling.Schedule')
def sync_schedule_to_employees(sender, instance, created, **kwargs):
    from account.models import Employee
    name_lower = instance.name.lower()

    if 'assistant ii' in name_lower:
        role = 'ASSISTANT_II'
    elif 'assistant i' in name_lower:
        role = 'ASSISTANT_I'
    else:
        return

    employees = Employee.objects.filter(role=role, is_active=True)
    instance.members.add(*employees)
