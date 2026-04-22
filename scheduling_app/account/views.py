from django.shortcuts import render
from scheduling.models import WeeklyAvailability, OperatingHours
from datetime import time
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import RegistrationForm

# Create your views here.
@login_required
def dashboard(request):
    if request.user.is_authenticated:
        # Fetch availability for the logged-in user
        all_availability = WeeklyAvailability.objects.filter(
            user=request.user
        ).order_by('day_of_week', 'start_time')
        
        # Define days and work hours
        days = [
            ('MON', 'Monday'),
            ('TUE', 'Tuesday'),
            ('WED', 'Wednesday'),
            ('THU', 'Thursday'),
            ('FRI', 'Friday'),
        ]
        
        # Get operating hours from database, or use defaults
        operating_hours = {}
        try:
            for day_code, day_name in days:
                oh = OperatingHours.objects.get(day_of_week=day_code)
                operating_hours[day_code] = {'start': oh.start_time, 'end': oh.end_time}
        except OperatingHours.DoesNotExist:
            # Fallback to default hours if not set in database
            for day_code, day_name in days:
                operating_hours[day_code] = {'start': time(8, 0), 'end': time(18, 0)}
        
        # Use the first day's operating hours for the calendar (assuming same hours each day)
        start_hour = operating_hours[days[0][0]]['start'].hour
        end_hour = operating_hours[days[0][0]]['end'].hour
        
        # Create 15-minute increment calendar grid with 12-hour format
        minutes_slots = []
        current_time = time(start_hour, 0)
        while current_time < time(end_hour, 0):
            hour = current_time.hour
            minute = current_time.minute
            
            # Convert to 12-hour format
            if hour == 0:
                display_hour = 12
                period = 'AM'
            elif hour < 12:
                display_hour = hour
                period = 'AM'
            elif hour == 12:
                display_hour = 12
                period = 'PM'
            else:
                display_hour = hour - 12
                period = 'PM'
            
            display = f"{display_hour}:{minute:02d} {period}"
            minutes_slots.append({
                'time': current_time,
                'display': display,
            })
            # Add 15 minutes
            minutes_int = current_time.hour * 60 + current_time.minute + 15
            new_hour = minutes_int // 60
            new_minute = minutes_int % 60
            current_time = time(new_hour, new_minute)
        
        # Build calendar grid - each cell contains availability info
        calendar = []
        for slot in minutes_slots:
            current_slot_time = slot['time']
            next_slot_time_minutes = current_slot_time.hour * 60 + current_slot_time.minute + 15
            next_hour = next_slot_time_minutes // 60
            next_minute = next_slot_time_minutes % 60
            next_slot_time = time(next_hour, next_minute) if next_hour < 24 else time(23, 59)
            
            row = {'slot': slot, 'days': {}}
            
            for day_code, day_name in days:
                # Find availabilities that overlap with this 15-minute slot
                availabilities = []
                for avail in all_availability.filter(day_of_week=day_code):
                    # Check if availability overlaps with this 15-minute slot
                    if avail.start_time <= current_slot_time and avail.end_time > current_slot_time:
                        availabilities.append(avail)
                
                row['days'][day_code] = availabilities
            
            calendar.append(row)
        
        context = {
            'calendar': calendar,
            'days': days,
            'operating_hours': operating_hours,
            'start_hour': start_hour,
            'end_hour': end_hour,
        }
    else:
        context = {
            'calendar': [],
            'days': [],
            'availability_blocks': {},
        }
    
    return render(request, 'account/dashboard.html', context)

@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def registration(request):
    if request.method == 'POST':
        user_form = RegistrationForm(request.POST)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.save()
            return render(
                request,
                'account/register_done.html',
                {'new_user':new_user}
            )
    else:
        user_form = RegistrationForm()
    return render(
        request,
        'account/register.html',
        {'user_form': user_form}
    )

