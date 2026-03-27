import os
import sys
import django
from datetime import time

# Add the Django project directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scheduling_app'))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scheduling_app.settings')
django.setup()

from account.models import Employee, WeeklyAvailability, Subject

def seed_database():
    # Define relevant subjects for seed data
    relevant_subjects = {
        'MTH': 'Math',
        'SCI': 'Science', 
        'WRI': 'Writing',
    }
    
    # Create Subject objects only for relevant subjects
    subjects_dict = {}
    for code, name in relevant_subjects.items():
        subject, created = Subject.objects.get_or_create(
            code=code,
            defaults={'name': name}
        )
        subjects_dict[code] = subject
        print(f"{'Created' if created else 'Found'} subject: {subject.name}")
    
    # Create test employees
    employees = [
        {
            'username': 'admin_user',
            'password': 'adminpass123',
            'first_name': 'Admin',
            'last_name': 'User',
            'email': 'admin@example.com',
            'role': Employee.Role.admin,
            'department': Employee.Department.director,
            'subjects': [],
        },
        {
            'username': 'scheduler_user',
            'password': 'schedpass123',
            'first_name': 'Scheduler',
            'last_name': 'User',
            'email': 'scheduler@example.com',
            'role': Employee.Role.scheduler,
            'department': Employee.Department.supervisor,
            'subjects': [],
        },
        {
            'username': 'math_tutor',
            'password': 'tutorpass123',
            'first_name': 'Math',
            'last_name': 'Tutor',
            'email': 'math.tutor@example.com',
            'role': Employee.Role.employee,
            'department': Employee.Department.tutor,
            'subjects': ['MTH'],
        },
        {
            'username': 'science_tutor',
            'password': 'tutorpass123',
            'first_name': 'Science',
            'last_name': 'Tutor',
            'email': 'science.tutor@example.com',
            'role': Employee.Role.employee,
            'department': Employee.Department.tutor,
            'subjects': ['SCI'],
        },
        {
            'username': 'writing_coach',
            'password': 'coachpass123',
            'first_name': 'Writing',
            'last_name': 'Coach',
            'email': 'writing.coach@example.com',
            'role': Employee.Role.employee,
            'department': Employee.Department.arc_assist_one,
            'subjects': ['WRI'],
        },
    ]

    created_employees = []
    for emp_data in employees:
        subjects = emp_data.pop('subjects')
        employee, created = Employee.objects.get_or_create(
            username=emp_data['username'],
            defaults={
                'first_name': emp_data['first_name'],
                'last_name': emp_data['last_name'],
                'email': emp_data['email'],
                'role': emp_data['role'],
                'department': emp_data['department'],
            }
        )
        if created:
            employee.set_password(emp_data['password'])
            employee.save()
        
        # Add subjects to the employee
        for subject_code in subjects:
            employee.subjects.add(subjects_dict[subject_code])
        
        created_employees.append(employee)
        subject_names = ', '.join([s.name for s in employee.subjects.all()]) or 'None'
        print(f"{'Created' if created else 'Found'} employee: {employee.username} (Subjects: {subject_names})")

    # Create weekly availabilities with 15-minute increments
    availabilities = [
        # Admin user - various times for testing
        {
            'user': 'admin_user',
            'day_of_week': WeeklyAvailability.DayOfWeek.MONDAY,
            'start_time': time(9, 0),
            'end_time': time(11, 30),
            'availability_type': WeeklyAvailability.AvailabilityType.PREFERRED,
        },
        {
            'user': 'admin_user',
            'day_of_week': WeeklyAvailability.DayOfWeek.WEDNESDAY,
            'start_time': time(14, 0),
            'end_time': time(17, 0),
            'availability_type': WeeklyAvailability.AvailabilityType.AVAILABLE,
        },
        # Math tutor - Monday morning (8:00-12:00)
        {
            'user': 'math_tutor',
            'day_of_week': WeeklyAvailability.DayOfWeek.MONDAY,
            'start_time': time(8, 0),
            'end_time': time(12, 0),
            'availability_type': WeeklyAvailability.AvailabilityType.AVAILABLE,
        },
        # Math tutor - Wednesday afternoon (13:00-15:30)
        {
            'user': 'math_tutor',
            'day_of_week': WeeklyAvailability.DayOfWeek.WEDNESDAY,
            'start_time': time(13, 0),
            'end_time': time(15, 30),
            'availability_type': WeeklyAvailability.AvailabilityType.PREFERRED,
        },
        # Science tutor - Tuesday morning (9:15-12:00)
        {
            'user': 'science_tutor',
            'day_of_week': WeeklyAvailability.DayOfWeek.TUESDAY,
            'start_time': time(9, 15),
            'end_time': time(12, 0),
            'availability_type': WeeklyAvailability.AvailabilityType.AVAILABLE,
        },
        # Science tutor - Thursday afternoon (14:00-16:00)
        {
            'user': 'science_tutor',
            'day_of_week': WeeklyAvailability.DayOfWeek.THURSDAY,
            'start_time': time(14, 0),
            'end_time': time(16, 0),
            'availability_type': WeeklyAvailability.AvailabilityType.AVAILABLE,
        },
        # Writing coach - Tuesday afternoon (13:45-15:15)
        {
            'user': 'writing_coach',
            'day_of_week': WeeklyAvailability.DayOfWeek.TUESDAY,
            'start_time': time(13, 45),
            'end_time': time(15, 15),
            'availability_type': WeeklyAvailability.AvailabilityType.PREFERRED,
        },
        # Writing coach - Friday morning (10:00-12:30)
        {
            'user': 'writing_coach',
            'day_of_week': WeeklyAvailability.DayOfWeek.FRIDAY,
            'start_time': time(10, 0),
            'end_time': time(12, 30),
            'availability_type': WeeklyAvailability.AvailabilityType.AVAILABLE,
        },
    ]

    for avail_data in availabilities:
        user = Employee.objects.get(username=avail_data['user'])
        availability, created = WeeklyAvailability.objects.get_or_create(
            user=user,
            day_of_week=avail_data['day_of_week'],
            start_time=avail_data['start_time'],
            end_time=avail_data['end_time'],
            defaults={'availability_type': avail_data['availability_type']}
        )
        print(f"{'Created' if created else 'Found'} availability: {availability}")

    print("Database seeding completed!")

if __name__ == '__main__':
    seed_database()
