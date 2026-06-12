from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory
from django.utils.dateparse import parse_date
from datetime import time, date, timedelta
import json

from .models import WeeklyAvailability, OperatingHours, DayOfWeek, ScheduleEntry, DateOperatingHours, Schedule
from .forms import OpenHoursForm, DateOperatingHoursForm


PARTTIME_WEEKLY_MAX = 19.5  # hours — applies to all part-time employees


def _loc_slug(loc):
    """Turn a location label into a safe string for input names/IDs."""
    return loc.lower().replace(' ', '_').replace('-', '_').replace('/', '_')


EMPLOYEE_PALETTE = [
    '#1565C0',  # Blue
    '#2E7D32',  # Green
    '#E65100',  # Deep Orange
    '#6A1B9A',  # Purple
    '#B71C1C',  # Red
    '#00695C',  # Teal
    '#AD1457',  # Pink
    '#558B2F',  # Olive Green
    '#4E342E',  # Brown
    '#37474F',  # Blue Grey
    '#F9A825',  # Amber
    '#00838F',  # Cyan
]


# ── helpers ──────────────────────────────────────────────────────────────────

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


_DOW_CODE = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}


def _get_operating_hours_for_date(d):
    """Return (start_time, end_time, is_closed) for a specific date.
    Checks DateOperatingHours first, falls back to weekly OperatingHours defaults."""
    try:
        doh = DateOperatingHours.objects.get(date=d)
        if doh.is_closed:
            return None, None, True
        return doh.start_time, doh.end_time, False
    except DateOperatingHours.DoesNotExist:
        pass

    dow = _DOW_CODE.get(d.weekday())
    if dow:
        try:
            oh = OperatingHours.objects.get(day_of_week=dow)
            return oh.start_time, oh.end_time, False
        except OperatingHours.DoesNotExist:
            pass

    # System default if nothing configured
    return time(8, 0), time(17, 0), False


def _week_start(d):
    """Return Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())

def _is_scheduler_or_admin(user):
    return user.is_authenticated and (
        user.role == 'ADMIN' or user.scheduler_of.exists()
    )

def _is_admin(user):
    return user.is_authenticated and user.role == 'ADMIN'

# ── availability ─────────────────────────────────────────────────────────────

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

    all_starts = [operating_hours[day]['start'] for day, _ in days]
    all_ends = [operating_hours[day]['end'] for day, _ in days]
    grid_start = min(all_starts)
    grid_end = max(all_ends)
    slots = _build_time_slots(grid_start, grid_end)

    if request.method == 'POST':
        WeeklyAvailability.objects.filter(user=request.user).delete()

        for day_code, _ in days:
            block_start = None
            block_type = None

            for slot in slots:
                key = f"slot_{day_code}_{slot.hour:02d}_{slot.minute:02d}"
                oh = operating_hours[day_code]
                in_hours = oh['start'] <= slot < oh['end']
                slot_type = request.POST.get(key, '') if in_hours else ''

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
            oh = operating_hours[day_code]
            in_hours = oh['start'] <= slot < oh['end']
            cell_type = ''
            if in_hours:
                for avail in existing:
                    if avail.day_of_week == day_code and avail.start_time <= slot < avail.end_time:
                        cell_type = avail.availability_type
                        break
            row['days'][day_code] = {'type': cell_type, 'in_hours': in_hours}
        grid.append(row)

    context = {
        'grid': grid,
        'days': days,
        'start_hour': grid_start.hour,
        'end_hour': grid_end.hour,
    }
    return render(request, 'scheduling/availability.html', context)


# ── operating hours (admin, calendar-aware) ───────────────────────────────────

@login_required
@user_passes_test(_is_admin)
def operating_hours(request):
    days = [d[0] for d in DayOfWeek.choices]

    for day in days:
        OperatingHours.objects.get_or_create(
            day_of_week=day,
            defaults={'start_time': time(8, 0), 'end_time': time(17, 0)}
        )

    OperatingHoursFormSet = modelformset_factory(OperatingHours, form=OpenHoursForm, extra=0)
    queryset = OperatingHours.objects.all()

    if request.method == 'POST' and 'save_defaults' in request.POST:
        formset = OperatingHoursFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Default operating hours updated.")
            return redirect('scheduling:operating_hours')
        date_form = DateOperatingHoursForm()
    elif request.method == 'POST' and 'add_special' in request.POST:
        date_form = DateOperatingHoursForm(request.POST)
        if date_form.is_valid():
            date_form.save()
            messages.success(request, "Special date hours added.")
            return redirect('scheduling:operating_hours')
        formset = OperatingHoursFormSet(queryset=queryset)
    else:
        formset = OperatingHoursFormSet(queryset=queryset)
        date_form = DateOperatingHoursForm()

    # Upcoming special date overrides (next 90 days)
    today = date.today()
    special_hours = DateOperatingHours.objects.filter(date__gte=today).order_by('date')[:30]

    return render(request, 'scheduling/operating_hours.html', {
        'formset': formset,
        'date_form': date_form,
        'special_hours': special_hours,
    })


@login_required
@user_passes_test(_is_admin)
def delete_special_hours(request, pk):
    entry = get_object_or_404(DateOperatingHours, pk=pk)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Special date removed.")
    return redirect('scheduling:operating_hours')


# ── schedule builder (schedulers + admins, drag-to-paint grid) ───────────────

@login_required
@user_passes_test(_is_scheduler_or_admin)
def schedule_builder(request):
    from account.models import Employee

    today = date.today()
    week_start = parse_date(request.GET.get('week', '')) or _week_start(today)
    week_dates = [week_start + timedelta(days=i) for i in range(5)]
    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    is_admin = request.user.role == 'ADMIN'
    if is_admin:
        allowed_schedules = list(Schedule.objects.all().order_by('name'))
    else:
        allowed_schedules = list(request.user.scheduler_of.all().order_by('name'))

    # Active schedule (defaults to first in list)
    schedule_pk_param = request.GET.get('schedule') or (str(allowed_schedules[0].pk) if allowed_schedules else '')
    active_schedule = next((s for s in allowed_schedules if str(s.pk) == schedule_pk_param), None)
    if not active_schedule and allowed_schedules:
        active_schedule = allowed_schedules[0]
        schedule_pk_param = str(active_schedule.pk)

    # Stable per-employee colors across all allowed employees
    all_allowed_employees = list(
        Employee.objects.filter(member_of__in=allowed_schedules)
        .distinct().order_by('pk')
    ) if not is_admin else list(Employee.objects.all().order_by('pk'))
    employee_colors = {
        e.pk: EMPLOYEE_PALETTE[i % len(EMPLOYEE_PALETTE)]
        for i, e in enumerate(all_allowed_employees)
    }

    # date → day abbreviation (MON/TUE/…) for the current week
    date_day_map = {d.isoformat(): d.strftime('%a').upper() for d in week_dates}

    # Employees visible in the sidebar — members of the active schedule
    if active_schedule:
        visible_employees = list(
            Employee.objects.filter(member_of=active_schedule)
            .distinct().order_by('last_name', 'first_name')
        )
    else:
        visible_employees = []

    # Availability data for visible employees (keyed by emp pk → day → list of blocks)
    avail_data = {}
    all_avail = WeeklyAvailability.objects.filter(user__in=visible_employees).order_by('start_time')
    for a in all_avail:
        avail_data.setdefault(str(a.user_id), {}).setdefault(a.day_of_week, []).append({
            'start': a.start_time.strftime('%H:%M'),
            'end': a.end_time.strftime('%H:%M'),
            'type': a.availability_type,
        })

    dept_locs = ['']
    has_locs = False

    # Already-scheduled entries for visible employees on OTHER schedules this week
    # — used to show conflict overlay in JS
    if visible_employees:
        conflict_qs = ScheduleEntry.objects.filter(
            user__in=visible_employees, date__in=week_dates,
        ).exclude(schedule=active_schedule)
        conflict_data = {}
        for e in conflict_qs.select_related('user'):
            conflict_data.setdefault(str(e.user_id), []).append({
                'date': e.date.isoformat(),
                'start': e.start_time.strftime('%H:%M'),
                'end': e.end_time.strftime('%H:%M'),
            })
    else:
        conflict_data = {}

    # Part-time flag + hours already scheduled in other contexts this week
    # (used by the frontend hours counter and backend validation alike)
    parttime_flags = {}
    other_hours_map = {}
    if visible_employees:
        for emp in visible_employees:
            is_pt = emp.part_time
            parttime_flags[emp.pk] = is_pt
            if is_pt:
                total_mins = sum(
                    (e.end_time.hour * 60 + e.end_time.minute)
                    - (e.start_time.hour * 60 + e.start_time.minute)
                    for e in conflict_qs.filter(user=emp)
                )
                other_hours_map[emp.pk] = round(total_mins / 60, 2)
            else:
                other_hours_map[emp.pk] = 0

    # Operating hours per day
    day_hours = {}
    for d in week_dates:
        start, end, closed = _get_operating_hours_for_date(d)
        day_hours[d] = {'start': start, 'end': end, 'closed': closed}

    open_days = [(h['start'], h['end']) for h in day_hours.values() if not h['closed'] and h['start']]
    grid_start, grid_end = (
        min(h[0] for h in open_days), max(h[1] for h in open_days)
    ) if open_days else (time(8, 0), time(17, 0))
    slots = _build_time_slots(grid_start, grid_end)

    # ── POST: rebuild schedule for this schedule/week ────────────────────────
    if request.method == 'POST':
        post_schedule_pk = request.POST.get('active_schedule_pk', schedule_pk_param)
        post_schedule = next((s for s in allowed_schedules if str(s.pk) == post_schedule_pk), active_schedule)
        post_emps = list(
            Employee.objects.filter(member_of=post_schedule).distinct()
        ) if post_schedule else []
        emp_lookup = {str(e.pk): e for e in post_emps}

        # ── Part-time hour-limit check (before any DB changes) ────────────────
        new_slots = {}   # emp_pk_str → set of (date_iso, slot_key)
        for d in week_dates:
            dh = day_hours[d]
            if dh['closed'] or not dh['start']:
                continue
            for slot in slots:
                key = f"slot_{d.isoformat()}_{slot.hour:02d}_{slot.minute:02d}"
                epk = request.POST.get(key, '')
                if epk and epk in emp_lookup:
                    new_slots.setdefault(epk, set()).add(
                        (d.isoformat(), f"{slot.hour:02d}_{slot.minute:02d}")
                    )

        violations = []
        for epk, slot_set in new_slots.items():
            emp = emp_lookup[epk]
            if not emp.part_time:
                continue
            new_mins = len(slot_set) * 15
            other_qs = ScheduleEntry.objects.filter(
                user=emp, date__in=week_dates
            ).exclude(schedule=post_schedule)
            other_mins = sum(
                (e.end_time.hour * 60 + e.end_time.minute)
                - (e.start_time.hour * 60 + e.start_time.minute)
                for e in other_qs
            )
            total_hrs = (new_mins + other_mins) / 60
            if total_hrs > PARTTIME_WEEKLY_MAX:
                violations.append(
                    f"{emp.first_name} {emp.last_name}: {total_hrs:.1f} hrs scheduled "
                    f"(limit {PARTTIME_WEEKLY_MAX})"
                )

        if violations:
            for v in violations:
                messages.error(request, f"Over weekly limit — {v}")
            redirect_url = f"?week={week_start.isoformat()}&schedule={post_schedule_pk}"
            return redirect(f"{request.path}{redirect_url}")

        # Delete existing entries for this schedule this week, then rebuild
        ScheduleEntry.objects.filter(date__in=week_dates, schedule=post_schedule).delete()

        for d in week_dates:
            dh = day_hours[d]
            if dh['closed'] or not dh['start']:
                continue
            emp_slots = {}
            for slot in slots:
                key = f"slot_{d.isoformat()}_{slot.hour:02d}_{slot.minute:02d}"
                emp_pk_str = request.POST.get(key, '')
                if emp_pk_str and emp_pk_str in emp_lookup:
                    emp_slots[slot] = emp_pk_str
            _slots_to_entries(emp_slots, slots, post_schedule, d, emp_lookup, request.user)

        messages.success(request, f"Schedule saved for {post_schedule}.")
        after_save = request.POST.get('redirect_after_save', '')
        redirect_url = after_save if after_save.startswith('?') else f"?week={week_start.isoformat()}&schedule={post_schedule_pk}"
        return redirect(f"{request.path}{redirect_url}")

    # ── GET: load existing entries into cell state ────────────────────────────
    entries_qs = ScheduleEntry.objects.filter(
        date__in=week_dates, schedule=active_schedule,
    ).select_related('user') if active_schedule else []
    entries = list(entries_qs)

    # cell_state[(date_iso, slot_key, loc_slug)] → {emp_pk, color}
    cell_state = {}
    for entry in entries:
        ls = _loc_slug(entry.location)
        color = employee_colors.get(entry.user.pk, '#999')
        for slot in slots:
            if entry.start_time <= slot < entry.end_time:
                sk = f"{slot.hour:02d}_{slot.minute:02d}"
                cell_state[(entry.date.isoformat(), sk, ls)] = {
                    'emp_pk': str(entry.user.pk),
                    'color': color,
                }

    # Build flat cell list per grid row
    num_locs = len(dept_locs)
    total_day_cols = 5 * num_locs
    col_template = f"72px repeat({total_day_cols}, 1fr)"

    # Precompute day × location header cells
    day_header_cols = []
    loc_header_cells = []
    for d in week_dates:
        day_header_cols.append({
            'date_iso': d.isoformat(),
            'label': d.strftime('%a'),
            'date_num': d.strftime('%-d'),
            'month_abbr': d.strftime('%b'),
            'is_today': d == today,
            'closed': day_hours[d]['closed'],
            'span': num_locs,
        })
        for loc in dept_locs:
            loc_header_cells.append({'loc': loc, 'date_iso': d.isoformat()})

    grid = []
    for slot in slots:
        sk = f"{slot.hour:02d}_{slot.minute:02d}"
        cells = []
        for d in week_dates:
            dh = day_hours[d]
            in_hours = not dh['closed'] and dh['start'] is not None and dh['start'] <= slot < dh['end']
            for loc in dept_locs:
                ls = _loc_slug(loc)
                c = cell_state.get((d.isoformat(), sk, ls), {})
                if has_locs:
                    inp_name = f"slot_{d.isoformat()}_{sk}_{ls}"
                    inp_id = f"inp_{d.isoformat()}_{sk}_{ls}"
                else:
                    inp_name = f"slot_{d.isoformat()}_{sk}"
                    inp_id = f"inp_{d.isoformat()}_{sk}"
                cells.append({
                    'date_iso': d.isoformat(),
                    'loc_slug': ls,
                    'in_hours': in_hours,
                    'emp_pk': c.get('emp_pk', ''),
                    'color': c.get('color', ''),
                    'inp_name': inp_name,
                    'inp_id': inp_id,
                    'value': c['emp_pk'] if c.get('emp_pk') else '',
                })
        grid.append({
            'time': slot, 'slot_key': sk,
            'display': _slot_display(slot),
            'show_label': slot.minute == 0,
            'cells': cells,
        })

    return render(request, 'scheduling/schedule_builder.html', {
        'week_start': week_start,
        'week_label': f"{week_start.strftime('%b %-d')} – {week_dates[-1].strftime('%b %-d, %Y')}",
        'prev_week': prev_week, 'next_week': next_week,
        'col_template': col_template,
        'day_header_cols': day_header_cols,
        'loc_header_cells': loc_header_cells,
        'has_locs': has_locs,
        'grid': grid,
        'allowed_schedules': allowed_schedules,
        'visible_employees': visible_employees,
        'employee_colors': employee_colors,
        'employee_colors_json': json.dumps(employee_colors),
        'active_schedule': active_schedule,
        'active_schedule_pk': schedule_pk_param,
        'employee_availability_json': json.dumps(avail_data),
        'employee_conflicts_json': json.dumps(conflict_data),
        'date_day_map_json': json.dumps(date_day_map),
        'employee_is_parttime_json': json.dumps({str(k): v for k, v in parttime_flags.items()}),
        'employee_other_hours_json': json.dumps({str(k): v for k, v in other_hours_map.items()}),
        'is_admin': is_admin, 'today': today,
    })


def _slots_to_entries(emp_slots, all_slots, schedule, d, emp_lookup, created_by):
    """Convert a {slot: emp_pk_str} mapping into contiguous ScheduleEntry objects."""
    by_emp = {}
    for slot, epk in emp_slots.items():
        by_emp.setdefault(epk, []).append(slot)

    for epk, slot_list in by_emp.items():
        slot_list.sort()
        emp = emp_lookup[epk]
        block_start = None
        prev_slot = None
        for slot in slot_list:
            if block_start is None:
                block_start = slot
            elif prev_slot is not None:
                expected = time(
                    (prev_slot.hour * 60 + prev_slot.minute + 15) // 60,
                    (prev_slot.hour * 60 + prev_slot.minute + 15) % 60,
                )
                if slot != expected:
                    end_t = time(
                        (prev_slot.hour * 60 + prev_slot.minute + 15) // 60,
                        (prev_slot.hour * 60 + prev_slot.minute + 15) % 60,
                    )
                    ScheduleEntry.objects.create(
                        user=emp, schedule=schedule,
                        date=d, start_time=block_start, end_time=end_t,
                        created_by=created_by,
                    )
                    block_start = slot
            prev_slot = slot

        if block_start is not None and prev_slot is not None:
            end_t = time(
                (prev_slot.hour * 60 + prev_slot.minute + 15) // 60,
                (prev_slot.hour * 60 + prev_slot.minute + 15) % 60,
            )
            if block_start < end_t:
                ScheduleEntry.objects.create(
                    user=emp, schedule=schedule,
                    date=d, start_time=block_start, end_time=end_t,
                    created_by=created_by,
                )
