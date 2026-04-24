import os
import sys
import django
from datetime import date, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scheduling_app'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scheduling_app.settings')
django.setup()

from account.models import Employee, Subject, Department
from scheduling.models import WeeklyAvailability, OperatingHours, DayOfWeek


def seed_subjects():
    data = [
        ('MTH', 'Math'),
        ('SCI', 'Science'),
        ('SPC', 'Speech'),
        ('WRI', 'Writing'),
        ('ACC', 'Accounting'),
        ('CIS', 'Computer Science'),
        ('LAN', 'Language'),
        ('ACD', 'Academic Coach'),
        ('MTC', 'Math Coach'),
        ('AEA', 'AEA - Academic Coach'),
    ]
    result = {}
    for code, name in data:
        obj, created = Subject.objects.get_or_create(code=code, defaults={'name': name})
        result[code] = obj
        print(f"{'Created' if created else 'Found'} subject: {obj.name}")
    return result


def seed_departments():
    names = ['New Hire', 'Tutor', 'Arc Assistant I', 'Arc Assistant II', 'Supervisor', 'Director']
    result = {}
    for name in names:
        obj, created = Department.objects.get_or_create(name=name)
        result[name] = obj
        print(f"{'Created' if created else 'Found'} department: {obj.name}")
    return result


def seed_operating_hours():
    hours = [
        ('MON', time(8, 0), time(17, 0)),
        ('TUE', time(8, 0), time(17, 0)),
        ('WED', time(8, 0), time(17, 0)),
        ('THU', time(8, 0), time(17, 0)),
        ('FRI', time(8, 0), time(17, 0)),
    ]
    for day, start, end in hours:
        obj, created = OperatingHours.objects.get_or_create(
            day_of_week=day,
            defaults={'start_time': start, 'end_time': end}
        )
        print(f"{'Created' if created else 'Found'} operating hours: {obj}")


def seed_employees(subjects, departments):
    employees = [
        {
            'username': 'admin_user',
            'password': 'adminpass123',
            'first_name': 'Admin',
            'last_name': 'User',
            'email': 'admin@example.com',
            'birthdate': date(1980, 1, 15),
            'role': Employee.Role.admin,
            'departments': ['Director'],
            'subjects': [],
        },
        {
            'username': 'scheduler_user',
            'password': 'schedpass123',
            'first_name': 'Scheduler',
            'last_name': 'User',
            'email': 'scheduler@example.com',
            'birthdate': date(1985, 6, 20),
            'role': Employee.Role.scheduler,
            'departments': ['Supervisor'],
            'subjects': [],
        },
        {
            'username': 'math_tutor',
            'password': 'tutorpass123',
            'first_name': 'Math',
            'last_name': 'Tutor',
            'email': 'math.tutor@example.com',
            'birthdate': date(1995, 3, 10),
            'role': Employee.Role.employee,
            'departments': ['Tutor'],
            'subjects': ['MTH'],
        },
        {
            'username': 'science_tutor',
            'password': 'tutorpass123',
            'first_name': 'Science',
            'last_name': 'Tutor',
            'email': 'science.tutor@example.com',
            'birthdate': date(1997, 8, 5),
            'role': Employee.Role.employee,
            'departments': ['Tutor'],
            'subjects': ['SCI'],
        },
        {
            'username': 'writing_coach',
            'password': 'coachpass123',
            'first_name': 'Writing',
            'last_name': 'Coach',
            'email': 'writing.coach@example.com',
            'birthdate': date(1993, 11, 22),
            'role': Employee.Role.employee,
            'departments': ['Arc Assistant I'],
            'subjects': ['WRI'],
        },
    ]

    result = []
    for emp_data in employees:
        dept_names = emp_data.pop('departments')
        subject_codes = emp_data.pop('subjects')
        password = emp_data.pop('password')

        employee, created = Employee.objects.get_or_create(
            username=emp_data['username'],
            defaults={k: v for k, v in emp_data.items()}
        )
        if created:
            employee.set_password(password)
            employee.save()

        employee.departments.set([departments[n] for n in dept_names])
        employee.subjects.set([subjects[c] for c in subject_codes])

        result.append(employee)
        dept_display = ', '.join(dept_names) or 'None'
        subj_display = ', '.join([subjects[c].name for c in subject_codes]) or 'None'
        print(f"{'Created' if created else 'Found'} employee: {employee.username} (Departments: {dept_display}, Subjects: {subj_display})")

    return result


def seed_availability(employees_by_username):
    availabilities = [
        ('admin_user',    'MON', time(9, 0),  time(11, 30), WeeklyAvailability.AvailabilityType.PREFERRED),
        ('admin_user',    'WED', time(14, 0), time(17, 0),  WeeklyAvailability.AvailabilityType.AVAILABLE),
        ('math_tutor',   'MON', time(8, 0),  time(12, 0),  WeeklyAvailability.AvailabilityType.AVAILABLE),
        ('math_tutor',   'WED', time(13, 0), time(15, 30), WeeklyAvailability.AvailabilityType.PREFERRED),
        ('science_tutor','TUE', time(9, 15), time(12, 0),  WeeklyAvailability.AvailabilityType.AVAILABLE),
        ('science_tutor','THU', time(14, 0), time(16, 0),  WeeklyAvailability.AvailabilityType.AVAILABLE),
        ('writing_coach','TUE', time(13, 45),time(15, 15), WeeklyAvailability.AvailabilityType.PREFERRED),
        ('writing_coach','FRI', time(10, 0), time(12, 30), WeeklyAvailability.AvailabilityType.AVAILABLE),
    ]

    for username, day, start, end, avail_type in availabilities:
        user = employees_by_username[username]
        obj, created = WeeklyAvailability.objects.get_or_create(
            user=user,
            day_of_week=day,
            start_time=start,
            end_time=end,
            defaults={'availability_type': avail_type}
        )
        print(f"{'Created' if created else 'Found'} availability: {obj}")


def seed_database():
    print("--- Subjects ---")
    subjects = seed_subjects()

    print("\n--- Departments ---")
    departments = seed_departments()

    print("\n--- Operating Hours ---")
    seed_operating_hours()

    print("\n--- Employees ---")
    employees = seed_employees(subjects, departments)
    employees_by_username = {e.username: e for e in employees}

    print("\n--- Weekly Availability ---")
    seed_availability(employees_by_username)

    print("\nDatabase seeding completed!")


if __name__ == '__main__':
    seed_database()
