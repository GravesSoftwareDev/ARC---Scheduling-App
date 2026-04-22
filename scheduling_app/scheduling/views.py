from django.shortcuts import render, redirect
from .models import WeeklyAvailability, OperatingHours
from datetime import time
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory
from .forms import OpenHoursForm


def _build_time_slots(start_time, end_time):
    slots = []
    current = start_time
    while current < end_time:
        slots.append(current)
        total_minutes = current.hour * 60 + current.minute + 15
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

    grid_start = operating_hours[days[0][0]]['start']
    grid_end = operating_hours[days[0][0]]['end']
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
    return render(request, 'scheduling/availability.html', context)


@login_required
@user_passes_test(lambda u: u.role == 'ADMIN')
def operating_hours(request):
    days = [d[0] for d in OperatingHours.DayOfWeek.choices]

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
            return redirect('scheduling:operating_hours')
    else:
        formset = OperatingHoursFormSet(queryset=queryset)

    return render(request, 'scheduling/operating_hours.html', {'formset': formset})
