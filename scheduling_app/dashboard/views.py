from django.shortcuts import render
from django.http import HttpResponse
from scheduling.models import WeeklyAvailability, ScheduleEntry
from scheduling.views import MIN_AVAILABILITY_HOURS
from scheduling import hours
from datetime import time, date, timedelta, datetime, timezone as dt_timezone
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_date


_DOW_CODE = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}

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


def _week_start(d):
    return d - timedelta(days=d.weekday())




@login_required
def dashboard(request):
    """The logged-in landing page. Builds two independent grids for the
    requested week: the employee's actual scheduled shifts (`grid`) and their
    recurring weekly availability (`avail_grid`, day-of-week based, always
    the same regardless of which week is being viewed)."""
    today = date.today()
    week_param = request.GET.get('week')
    if week_param:
        week_start = parse_date(week_param)
        if not week_start:
            week_start = _week_start(today)
    else:
        week_start = _week_start(today)

    week_dates = [week_start + timedelta(days=i) for i in range(5)]  # Mon–Fri
    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    # Calendar-based schedule entries for this week
    schedule_entries = list(
        ScheduleEntry.objects.filter(
            user=request.user,
            date__in=week_dates
        ).select_related('schedule').order_by('date', 'start_time')
    )

    # Legend — unique schedules appearing this week
    seen_schedules = {}
    for e in schedule_entries:
        if e.schedule_id not in seen_schedules:
            seen_schedules[e.schedule_id] = {'label': e.schedule.name, 'color': e.schedule.color}
    schedule_legend = list(seen_schedules.values())

    # Operating hours per day
    day_hours = {}
    for d in week_dates:
        start, end, closed = hours.hours_for_date(d, request.user.role)
        day_hours[d] = {'start': start, 'end': end, 'closed': closed}

    # Grid bounds: span the earliest open to latest close across open days
    open_hours = [(h['start'], h['end']) for h in day_hours.values() if not h['closed'] and h['start']]
    if open_hours:
        grid_start = min(h[0] for h in open_hours)
        grid_end = max(h[1] for h in open_hours)
    else:
        grid_start = time(8, 0)
        grid_end = time(17, 0)

    slots = hours.build_slots(
        grid_start, grid_end,
        hours.span_edges((h['start'], h['end'], h['closed']) for h in day_hours.values()),
    )

    # Weekly availability (still day-of-week based)
    avail_list = list(WeeklyAvailability.objects.filter(user=request.user))

    total_availability_hours = sum(
        (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
        for a in avail_list
    ) / 60

    # Build calendar grid
    grid = []
    for idx, slot in enumerate(slots):
        row = {
            'time': slot,
            'display': _slot_display(slot),
            'show_label': slot.minute == 0 or idx == 0 or slot.minute % 30 != 0,
            'schedule': {},
            'avail': {},
        }
        for d in week_dates:
            dh = day_hours[d]
            in_hours = (
                not dh['closed']
                and dh['start'] is not None
                and dh['start'] <= slot < dh['end']
            )

            blocks = [
                e for e in schedule_entries
                if e.date == d and e.start_time <= slot < e.end_time
            ]
            row['schedule'][d.isoformat()] = {'in_hours': in_hours, 'blocks': blocks, 'closed': dh['closed']}

            # Availability uses day-of-week from the date
            dow = _DOW_CODE.get(d.weekday(), '')
            avail_type = ''
            if in_hours:
                for a in avail_list:
                    if a.day_of_week == dow and a.start_time <= slot < a.end_time:
                        avail_type = a.availability_type
                        break
            row['avail'][d.isoformat()] = {'in_hours': in_hours, 'type': avail_type}

        grid.append(row)

    # Weekly availability grid (for mini calendar – still day-of-week based)
    avail_days = [
        ('MON', 'Monday'), ('TUE', 'Tuesday'), ('WED', 'Wednesday'),
        ('THU', 'Thursday'), ('FRI', 'Friday'),
    ]
    role_weekly = hours.weekly_hours(request.user.role)
    avail_operating_hours = {
        day_code: {'start': role_weekly[day_code][0], 'end': role_weekly[day_code][1]}
        for day_code, _ in avail_days
    }

    avail_grid_start = min(v['start'] for v in avail_operating_hours.values())
    avail_grid_end = max(v['end'] for v in avail_operating_hours.values())
    avail_slots = hours.build_slots(
        avail_grid_start, avail_grid_end,
        {t for v in avail_operating_hours.values() for t in (v['start'], v['end'])},
    )

    avail_grid = []
    for idx, slot in enumerate(avail_slots):
        row = {'time': slot, 'display': _slot_display(slot), 'show_label': slot.minute == 0 or idx == 0 or slot.minute % 30 != 0, 'days': {}}
        for day_code, _ in avail_days:
            oh = avail_operating_hours[day_code]
            in_hours = oh['start'] <= slot < oh['end']
            cell_type = ''
            if in_hours:
                for a in avail_list:
                    if a.day_of_week == day_code and a.start_time <= slot < a.end_time:
                        cell_type = a.availability_type
                        break
            row['days'][day_code] = {'type': cell_type, 'in_hours': in_hours}
        avail_grid.append(row)

    # Build days_display list for the schedule header
    days_display = []
    for d in week_dates:
        days_display.append({
            'date': d,
            'date_iso': d.isoformat(),
            'label_full': d.strftime('%A'),
            'label_short': d.strftime('%a'),
            'label_num': str(d.day),
            'month_abbr': d.strftime('%b'),
            'is_today': d == today,
            'closed': day_hours[d]['closed'],
        })

    return render(request, 'dashboard/dashboard.html', {
        # Toggle to bring the weekly schedule calendar back to the dashboard;
        # while False, the availability calendar takes its place instead.
        'show_schedule': False,
        'grid': grid,
        'days_display': days_display,
        'avail_grid': avail_grid,
        'avail_days': avail_days,
        'total_availability_hours': total_availability_hours,
        'min_availability_hours': MIN_AVAILABILITY_HOURS,
        'below_min_availability': total_availability_hours < MIN_AVAILABILITY_HOURS,
        'has_schedule': bool(schedule_entries),
        'schedule_legend': schedule_legend,
        'week_start': week_start,
        'week_end': week_dates[-1],
        'week_label': f"{week_start.strftime('%b')} {week_start.day} – {week_dates[-1].strftime('%b')} {week_dates[-1].day}, {week_dates[-1].year}",
        'prev_week': prev_week,
        'next_week': next_week,
        'today': today,
    })


def _ics_escape(value):
    return value.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def _ics_fold(line):
    """Fold long ICS lines to max 75 octets per RFC 5545."""
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return line
    result = []
    while len(line.encode('utf-8')) > 75:
        chunk = line[:75]
        while len(chunk.encode('utf-8')) > 75:
            chunk = chunk[:-1]
        result.append(chunk)
        line = ' ' + line[len(chunk):]
    result.append(line)
    return '\r\n'.join(result)


@login_required
def export_schedule_ics(request):
    """Export every ScheduleEntry the logged-in employee is assigned to,
    across all schedules and all dates, as a single .ics file they can
    subscribe to (or import) in an external calendar app."""
    entries = (
        ScheduleEntry.objects
        .filter(user=request.user)
        .select_related('schedule')
        .order_by('date', 'start_time')
    )

    dtstamp = datetime.now(dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    user_slug = request.user.username

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//ARC Scheduling App//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]

    for entry in entries:
        # No trailing "Z" or TZID here on purpose — these are RFC 5545
        # "floating" local times, which is correct for a physical location's
        # posted schedule: the shift is at this wall-clock time regardless of
        # which timezone the viewer's calendar app is set to.
        dtstart = entry.date.strftime('%Y%m%d') + 'T' + entry.start_time.strftime('%H%M%S')
        dtend   = entry.date.strftime('%Y%m%d') + 'T' + entry.end_time.strftime('%H%M%S')
        uid     = f'scheduleentry-{entry.pk}-{user_slug}@arc-scheduling'
        summary = _ics_escape(entry.custom_label or entry.schedule.name)

        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{dtstamp}',
            f'DTSTART:{dtstart}',
            f'DTEND:{dtend}',
            f'SUMMARY:{summary}',
        ]
        if entry.location:
            lines.append(f'LOCATION:{_ics_escape(entry.location)}')
        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')

    content = '\r\n'.join(_ics_fold(line) for line in lines) + '\r\n'
    response = HttpResponse(content, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="arc-schedule-{user_slug}.ics"'
    return response
