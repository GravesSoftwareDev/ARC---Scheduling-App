from django.shortcuts import render, redirect
from .models import WeeklyAvailability, OperatingHours
from datetime import time
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory
from django.db.models import Case, When, IntegerField
from .forms import RegistrationForm, OpenHoursForm

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

def _build_time_slots(start_time, end_time):
    """Return a list of time objects at 15-minute intervals from start_time up to (not including) end_time."""
    slots = []
    current = start_time
    while current < end_time:
        slots.append(current)
        total_minutes = current.hour * 60 + current.minute + 15  # advance 15 min
        current = time(total_minutes // 60, total_minutes % 60)
    return slots


def _slot_display(t):
    h, m = t.hour, t.minute
    if h == 0:
        return f"12:{m:02d} AM"
    elif h < 12:
        return f"{h}:{m:02d} AM"
    elif h == 12:
        return f"12:{m:02d} PM"
    else:
        return f"{h - 12}:{m:02d} PM"


@login_required
def manage_availability(request):
    days = [
        ('MON', 'Monday'), ('TUE', 'Tuesday'), ('WED', 'Wednesday'),
        ('THU', 'Thursday'), ('FRI', 'Friday'),
    ]

    operating_hours = {}
    for day_code, _ in days:
        oh, _ = OperatingHours.objects.get_or_create(
            day_of_week=day_code,
            defaults={'start_time': time(8, 0), 'end_time': time(18, 0)},
        )
        operating_hours[day_code] = {'start': oh.start_time, 'end': oh.end_time}

    # All days share the same boundary for the grid
    grid_start = operating_hours[days[0][0]]['start']
    grid_end = operating_hours[days[0][0]]['end']
    # 15-minute slots spanning the operating day
    slots = _build_time_slots(grid_start, grid_end)

    if request.method == 'POST':
        WeeklyAvailability.objects.filter(user=request.user).delete()

        for day_code, _ in days:
            block_start = None
            block_type = None

            for slot in slots:
                key = f"slot_{day_code}_{slot.hour:02d}_{slot.minute:02d}"
                slot_type = request.POST.get(key, '')

                if slot_type in ('AVAILABLE', 'PREFERRED'):
                    if block_start is None:
                        block_start = slot
                        block_type = slot_type
                    elif slot_type != block_type:
                        # End current block, start a new one
                        WeeklyAvailability.objects.create(
                            user=request.user, day_of_week=day_code,
                            start_time=block_start, end_time=slot,
                            availability_type=block_type,
                        )
                        block_start = slot
                        block_type = slot_type
                else:
                    if block_start is not None:
                        WeeklyAvailability.objects.create(
                            user=request.user, day_of_week=day_code,
                            start_time=block_start, end_time=slot,
                            availability_type=block_type,
                        )
                        block_start = None
                        block_type = None

            # Close any block that runs to end of day
            if block_start is not None:
                last_slot = slots[-1]
                end_total = last_slot.hour * 60 + last_slot.minute + 15
                end_time = time(end_total // 60, end_total % 60)
                WeeklyAvailability.objects.create(
                    user=request.user, day_of_week=day_code,
                    start_time=block_start, end_time=end_time,
                    availability_type=block_type,
                )

        return redirect('dashboard:dashboard')

    # Prefill grid with saved availability
    existing = list(WeeklyAvailability.objects.filter(user=request.user))
    grid = []
    for slot in slots:
        row = {'time': slot, 'display': _slot_display(slot), 'days': {}}
        for day_code, _ in days:
            cell_type = ''
            for avail in existing:
                if avail.day_of_week == day_code and avail.start_time <= slot < avail.end_time:
                    cell_type = avail.availability_type
                    break
            row['days'][day_code] = cell_type
        grid.append(row)

    context = {
        'grid': grid,
        'days': days,
        'start_hour': grid_start.hour,
        'end_hour': grid_end.hour,
    }
    return render(request, 'account/availability.html', context)


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


@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def operating_hours(request):
    days = [d[0] for d in OperatingHours.DayOfWeek.choices]

    # Ensure an OperatingHours row exists for each day
    for day in days:
        OperatingHours.objects.get_or_create(
            day_of_week=day,
            defaults={'start_time': time(8, 0), 'end_time': time(18, 0)}
        )

    OperatingHoursFormSet = modelformset_factory(
        OperatingHours, form=OpenHoursForm, extra=0
    )
    queryset = OperatingHours.objects.all()

    if request.method == 'POST':
        formset = OperatingHoursFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            return redirect('dashboard:operating_hours')
    else:
        formset = OperatingHoursFormSet(queryset=queryset)

    return render(request, 'account/operating_hours.html', {'formset': formset})