from django.shortcuts import render
from scheduling.models import WeeklyAvailability, WeeklySchedule, OperatingHours
from datetime import time
from django.contrib.auth.decorators import login_required


def _build_time_slots(start_time, end_time):
    slots = []
    current = start_time
    while current < end_time:
        slots.append(current)
        total = current.hour * 60 + current.minute + 15
        current = time(total // 60, total % 60)
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
def dashboard(request):
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

    grid_start = min(operating_hours[d]['start'] for d, _ in days)
    grid_end = max(operating_hours[d]['end'] for d, _ in days)
    slots = _build_time_slots(grid_start, grid_end)

    schedule_list = list(
        WeeklySchedule.objects.filter(user=request.user).select_related('department')
    )

    seen = {}
    for s in schedule_list:
        if s.department_id not in seen:
            seen[s.department_id] = s.department
    schedule_departments = list(seen.values())
    avail_list = list(WeeklyAvailability.objects.filter(user=request.user))

    grid = []
    for slot in slots:
        row = {
            'time': slot,
            'display': _slot_display(slot),
            'show_label': slot.minute == 0,
            'schedule': {},
            'avail': {},
        }
        for day_code, _ in days:
            oh = operating_hours[day_code]
            in_hours = oh['start'] <= slot < oh['end']

            blocks = [
                s for s in schedule_list
                if s.day_of_week == day_code and s.start_time <= slot < s.end_time
            ]
            row['schedule'][day_code] = {'in_hours': in_hours, 'blocks': blocks}

            avail_type = ''
            if in_hours:
                for a in avail_list:
                    if a.day_of_week == day_code and a.start_time <= slot < a.end_time:
                        avail_type = a.availability_type
                        break
            row['avail'][day_code] = {'in_hours': in_hours, 'type': avail_type}

        grid.append(row)

    return render(request, 'dashboard/dashboard.html', {
        'grid': grid,
        'days': days,
        'has_schedule': bool(schedule_list),
        'schedule_departments': schedule_departments,
    })
