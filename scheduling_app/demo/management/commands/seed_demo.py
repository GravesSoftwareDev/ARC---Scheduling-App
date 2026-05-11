"""
Populate the database with realistic fake data for the portfolio demo.
Safe to run multiple times — static data uses get_or_create, dynamic data
(schedule entries and availability) is deleted and rebuilt.
"""
from datetime import date, time, timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from account.models import Department
from account.models import Employee
from account.models import Subject as AccountSubject
from scheduling.models import OperatingHours
from scheduling.models import ScheduleEntry
from scheduling.models import Subject as SchedSubject
from scheduling.models import WeeklyAvailability


_DEMO_USERS = [
    {'username': 'demo_admin',     'first_name': 'Morgan',  'last_name': 'Chen',     'role': 'ADMIN',     'email': 'demo_admin@example.com'},
    {'username': 'demo_scheduler', 'first_name': 'Jordan',  'last_name': 'Rivera',   'role': 'SCHEDULER', 'email': 'demo_scheduler@example.com'},
    {'username': 'demo_employee',  'first_name': 'Alex',    'last_name': 'Taylor',   'role': 'EMPLOYEE',  'email': 'demo_employee@example.com'},
]

_EXTRA_EMPLOYEES = [
    {'username': 'riley_brooks',   'first_name': 'Riley',   'last_name': 'Brooks',   'role': 'EMPLOYEE', 'email': 'riley@example.com'},
    {'username': 'casey_martinez', 'first_name': 'Casey',   'last_name': 'Martinez', 'role': 'EMPLOYEE', 'email': 'casey@example.com'},
    {'username': 'sam_patel',      'first_name': 'Sam',     'last_name': 'Patel',    'role': 'EMPLOYEE', 'email': 'sam@example.com'},
    {'username': 'jamie_wilson',   'first_name': 'Jamie',   'last_name': 'Wilson',   'role': 'EMPLOYEE', 'email': 'jamie@example.com'},
    {'username': 'drew_anderson',  'first_name': 'Drew',    'last_name': 'Anderson', 'role': 'EMPLOYEE', 'email': 'drew@example.com'},
    {'username': 'cameron_lee',    'first_name': 'Cameron', 'last_name': 'Lee',      'role': 'EMPLOYEE', 'email': 'cameron@example.com'},
    {'username': 'quinn_davis',    'first_name': 'Quinn',   'last_name': 'Davis',    'role': 'EMPLOYEE', 'email': 'quinn@example.com'},
    {'username': 'avery_thomas',   'first_name': 'Avery',   'last_name': 'Thomas',   'role': 'EMPLOYEE', 'email': 'avery@example.com'},
]


class Command(BaseCommand):
    help = 'Seed the database with demo data'

    def handle(self, *args, **options):
        self._seed_account_subjects()
        self._seed_departments_and_sched_subjects()
        self._seed_employees()
        self._seed_operating_hours()
        self._seed_availability()
        self._seed_schedule_entries()
        self.stdout.write(self.style.SUCCESS('Demo data seeded.'))

    # ── static reference data ─────────────────────────────────────────────────

    def _seed_account_subjects(self):
        for code, name in [
            ('MTH', 'Math'), ('SCI', 'Science'), ('WRI', 'Writing'),
            ('ACC', 'Accounting'), ('CIS', 'Computer Science'),
        ]:
            AccountSubject.objects.get_or_create(code=code, defaults={'name': name})

    def _seed_departments_and_sched_subjects(self):
        for name in ['Math Center', 'Tutoring Center', 'Writing Lab']:
            Department.objects.get_or_create(name=name)

        tc = Department.objects.get(name='Tutoring Center')
        wl = Department.objects.get(name='Writing Lab')
        mc = Department.objects.get(name='Math Center')

        for dept, name, locations, code in [
            (tc, 'Math',       'Drop-in,Coaching', 'MTH'),
            (tc, 'Writing',    'Drop-in,Coaching', 'WRI'),
            (tc, 'Science',    'Drop-in',          'SCI'),
            (wl, 'Writing',    'Drop-in,Coaching', 'WRI'),
            (mc, 'Math',       'Drop-in,Coaching', 'MTH'),
            (mc, 'Accounting', 'Drop-in',          'ACC'),
        ]:
            SchedSubject.objects.get_or_create(
                department=dept, name=name,
                defaults={'locations': locations, 'account_subject_code': code},
            )

    def _seed_employees(self):
        pw = make_password('DemoPass2024!')
        for u in _DEMO_USERS + _EXTRA_EMPLOYEES:
            emp, created = Employee.objects.get_or_create(
                username=u['username'],
                defaults={
                    'first_name': u['first_name'],
                    'last_name':  u['last_name'],
                    'role':       u['role'],
                    'email':      u['email'],
                    'password':   pw,
                    'is_active':  True,
                },
            )
            if not created and not emp.is_active:
                emp.is_active = True
                emp.save(update_fields=['is_active'])

        tc = Department.objects.get(name='Tutoring Center')
        wl = Department.objects.get(name='Writing Lab')
        mc = Department.objects.get(name='Math Center')

        dept_map = {
            'demo_employee':  [tc],
            'demo_scheduler': [tc, wl],
            'riley_brooks':   [tc, mc],
            'casey_martinez': [wl],
            'sam_patel':      [tc],
            'jamie_wilson':   [mc],
            'drew_anderson':  [tc],
            'cameron_lee':    [wl, tc],
            'quinn_davis':    [mc],
            'avery_thomas':   [mc, wl],
        }
        for username, depts in dept_map.items():
            Employee.objects.get(username=username).departments.set(depts)

        mth = AccountSubject.objects.get(code='MTH')
        sci = AccountSubject.objects.get(code='SCI')
        wri = AccountSubject.objects.get(code='WRI')
        acc = AccountSubject.objects.get(code='ACC')
        cis = AccountSubject.objects.get(code='CIS')

        subj_map = {
            'demo_employee':  [mth, wri],
            'riley_brooks':   [mth, sci],
            'casey_martinez': [wri],
            'sam_patel':      [mth, acc],
            'jamie_wilson':   [mth],
            'drew_anderson':  [mth, sci],
            'cameron_lee':    [wri, cis],
            'quinn_davis':    [mth, wri],
            'avery_thomas':   [mth],
        }
        for username, subjs in subj_map.items():
            Employee.objects.get(username=username).subjects.set(subjs)

    def _seed_operating_hours(self):
        for day in ['MON', 'TUE', 'WED', 'THU', 'FRI']:
            OperatingHours.objects.get_or_create(
                day_of_week=day,
                defaults={'start_time': time(8, 0), 'end_time': time(17, 0)},
            )

    # ── dynamic data (rebuilt each seed) ─────────────────────────────────────

    def _seed_availability(self):
        avail_config = {
            'demo_employee': [
                ('MON', time(9,  0), time(17, 0), 'AVAILABLE'),
                ('TUE', time(9,  0), time(17, 0), 'AVAILABLE'),
                ('WED', time(9,  0), time(17, 0), 'AVAILABLE'),
                ('THU', time(10, 0), time(16, 0), 'PREFERRED'),
                ('FRI', time(10, 0), time(16, 0), 'PREFERRED'),
            ],
            'riley_brooks': [
                ('MON', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('TUE', time(8,  0), time(12, 0), 'AVAILABLE'),
                ('TUE', time(13, 0), time(17, 0), 'AVAILABLE'),
                ('WED', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('THU', time(8,  0), time(17, 0), 'PREFERRED'),
                ('FRI', time(9,  0), time(15, 0), 'AVAILABLE'),
            ],
            'casey_martinez': [
                ('MON', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('WED', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('FRI', time(8,  0), time(17, 0), 'AVAILABLE'),
            ],
            'sam_patel': [
                ('MON', time(8,  0), time(13, 0), 'PREFERRED'),
                ('TUE', time(8,  0), time(13, 0), 'PREFERRED'),
                ('WED', time(8,  0), time(13, 0), 'PREFERRED'),
                ('THU', time(8,  0), time(13, 0), 'PREFERRED'),
                ('FRI', time(8,  0), time(13, 0), 'PREFERRED'),
            ],
            'jamie_wilson': [
                ('TUE', time(9,  0), time(17, 0), 'AVAILABLE'),
                ('WED', time(9,  0), time(17, 0), 'AVAILABLE'),
                ('THU', time(9,  0), time(17, 0), 'AVAILABLE'),
            ],
            'drew_anderson': [
                ('MON', time(10, 0), time(15, 0), 'AVAILABLE'),
                ('TUE', time(10, 0), time(15, 0), 'AVAILABLE'),
                ('WED', time(10, 0), time(15, 0), 'AVAILABLE'),
                ('THU', time(10, 0), time(15, 0), 'AVAILABLE'),
                ('FRI', time(10, 0), time(15, 0), 'AVAILABLE'),
            ],
            'cameron_lee': [
                ('MON', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('TUE', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('WED', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('THU', time(8,  0), time(17, 0), 'AVAILABLE'),
                ('FRI', time(8,  0), time(17, 0), 'AVAILABLE'),
            ],
            'quinn_davis': [
                ('MON', time(9,  0), time(16, 0), 'PREFERRED'),
                ('TUE', time(9,  0), time(16, 0), 'PREFERRED'),
                ('WED', time(9,  0), time(16, 0), 'PREFERRED'),
                ('THU', time(9,  0), time(16, 0), 'PREFERRED'),
                ('FRI', time(9,  0), time(16, 0), 'PREFERRED'),
            ],
            'avery_thomas': [
                ('MON', time(8,  0), time(12, 0), 'AVAILABLE'),
                ('WED', time(8,  0), time(12, 0), 'AVAILABLE'),
                ('WED', time(13, 0), time(17, 0), 'AVAILABLE'),
                ('FRI', time(13, 0), time(17, 0), 'AVAILABLE'),
            ],
        }

        for username, blocks in avail_config.items():
            emp = Employee.objects.get(username=username)
            WeeklyAvailability.objects.filter(user=emp).delete()
            for day, start, end, avtype in blocks:
                WeeklyAvailability.objects.create(
                    user=emp, day_of_week=day,
                    start_time=start, end_time=end,
                    availability_type=avtype,
                )

    def _seed_schedule_entries(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())

        tc = Department.objects.get(name='Tutoring Center')
        wl = Department.objects.get(name='Writing Lab')
        mc = Department.objects.get(name='Math Center')

        tc_math    = SchedSubject.objects.get(department=tc, name='Math')
        tc_writing = SchedSubject.objects.get(department=tc, name='Writing')
        tc_science = SchedSubject.objects.get(department=tc, name='Science')
        wl_writing = SchedSubject.objects.get(department=wl, name='Writing')
        mc_math    = SchedSubject.objects.get(department=mc, name='Math')

        emp = {u: Employee.objects.get(username=u) for u in [
            'demo_employee', 'demo_admin', 'riley_brooks', 'casey_martinez',
            'sam_patel', 'jamie_wilson', 'drew_anderson', 'cameron_lee',
            'quinn_davis', 'avery_thomas',
        ]}

        mon, tue, wed, thu, fri = [monday + timedelta(days=i) for i in range(5)]
        admin = emp['demo_admin']

        # (user, dept, subject, date, start, end, location)
        entries = [
            # Monday
            (emp['demo_employee'], tc, tc_math,    mon, time(9,  0), time(13, 0), 'Drop-in'),
            (emp['riley_brooks'],  tc, tc_math,    mon, time(8,  0), time(12, 0), 'Coaching'),
            (emp['sam_patel'],     tc, tc_math,    mon, time(10, 0), time(13, 0), 'Drop-in'),
            (emp['drew_anderson'], tc, tc_science, mon, time(10, 0), time(15, 0), 'Drop-in'),
            (emp['cameron_lee'],   wl, wl_writing, mon, time(9,  0), time(13, 0), 'Drop-in'),
            # Tuesday
            (emp['demo_employee'], tc, tc_writing, tue, time(9,  0), time(14, 0), 'Coaching'),
            (emp['cameron_lee'],   tc, tc_writing, tue, time(10, 0), time(14, 0), 'Drop-in'),
            (emp['casey_martinez'],wl, wl_writing, tue, time(9,  0), time(12, 0), 'Drop-in'),
            (emp['jamie_wilson'],  mc, mc_math,    tue, time(9,  0), time(13, 0), 'Drop-in'),
            (emp['quinn_davis'],   mc, mc_math,    tue, time(9,  0), time(14, 0), 'Coaching'),
            # Wednesday
            (emp['riley_brooks'],  tc, tc_math,    wed, time(8,  0), time(12, 0), 'Drop-in'),
            (emp['sam_patel'],     tc, tc_math,    wed, time(8,  0), time(13, 0), 'Coaching'),
            (emp['demo_employee'], tc, tc_writing, wed, time(13, 0), time(17, 0), 'Drop-in'),
            (emp['casey_martinez'],wl, wl_writing, wed, time(10, 0), time(15, 0), 'Coaching'),
            (emp['cameron_lee'],   wl, wl_writing, wed, time(13, 0), time(17, 0), 'Drop-in'),
            (emp['avery_thomas'],  mc, mc_math,    wed, time(8,  0), time(12, 0), 'Drop-in'),
            # Thursday
            (emp['drew_anderson'], tc, tc_science, thu, time(10, 0), time(15, 0), 'Drop-in'),
            (emp['riley_brooks'],  tc, tc_math,    thu, time(8,  0), time(12, 0), 'Drop-in'),
            (emp['jamie_wilson'],  mc, mc_math,    thu, time(9,  0), time(14, 0), 'Coaching'),
            (emp['quinn_davis'],   mc, mc_math,    thu, time(9,  0), time(16, 0), 'Drop-in'),
            # Friday
            (emp['demo_employee'], tc, tc_math,    fri, time(10, 0), time(16, 0), 'Drop-in'),
            (emp['sam_patel'],     tc, tc_math,    fri, time(8,  0), time(13, 0), 'Drop-in'),
            (emp['casey_martinez'],wl, wl_writing, fri, time(9,  0), time(14, 0), 'Coaching'),
            (emp['avery_thomas'],  mc, mc_math,    fri, time(13, 0), time(17, 0), 'Drop-in'),
            (emp['quinn_davis'],   mc, mc_math,    fri, time(9,  0), time(13, 0), 'Coaching'),
        ]

        week_dates = [mon, tue, wed, thu, fri]
        ScheduleEntry.objects.filter(date__in=week_dates).delete()

        for user, dept, subj, d, start, end, loc in entries:
            ScheduleEntry.objects.create(
                user=user, department=dept, subject=subj,
                date=d, start_time=start, end_time=end,
                location=loc, created_by=admin,
            )
