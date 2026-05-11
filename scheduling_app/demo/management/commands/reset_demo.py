"""
Reset all demo data back to its seeded state.
Run this on a nightly cron (e.g. Heroku Scheduler) to keep the demo clean.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from account.models import Employee
from scheduling.models import DateOperatingHours, ScheduleEntry, WeeklyAvailability


_ALL_DEMO_USERNAMES = [
    'demo_admin', 'demo_scheduler', 'demo_employee',
    'riley_brooks', 'casey_martinez', 'sam_patel',
    'jamie_wilson', 'drew_anderson', 'cameron_lee',
    'quinn_davis', 'avery_thomas',
]


class Command(BaseCommand):
    help = 'Reset demo data to its initial seeded state'

    def handle(self, *args, **options):
        ScheduleEntry.objects.all().delete()
        WeeklyAvailability.objects.all().delete()
        DateOperatingHours.objects.all().delete()
        # Remove all non-superuser employees so no real data lingers
        Employee.objects.filter(is_superuser=False).delete()
        call_command('seed_demo')
        self.stdout.write(self.style.SUCCESS('Demo reset complete.'))
