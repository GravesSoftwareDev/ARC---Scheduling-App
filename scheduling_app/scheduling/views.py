from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory
from django.utils.dateparse import parse_date
from datetime import time, date, timedelta
from collections import namedtuple
import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import WeeklyAvailability, OperatingHours, DayOfWeek, ScheduleEntry, DateOperatingHours, Schedule, ShiftLabel, LABEL_PALETTE, WeeklySchedule, AvailabilityWindow
from .forms import OpenHoursForm, DateOperatingHoursForm, EmployeePreferencesForm, AvailabilityWindowForm


PARTTIME_WEEKLY_MAX = 19.5  # hours — applies to all part-time employees
SLOT_MINUTES = 30  # granularity of the availability / schedule builder grids
LEAD_IN_MINUTES = 15  # the opening supervisor's window before the normal start
MIN_AVAILABILITY_HOURS = 10  # employees must mark at least this many hours to be schedulable


def _loc_slug(loc):
    """Turn a location label into a safe string for input names/IDs."""
    return loc.lower().replace(' ', '_').replace('-', '_').replace('/', '_')


EMPLOYEE_PALETTE = [
    '#C62828', '#AD1457', '#6A1B9A', '#4527A0', '#283593',
    '#1565C0', '#0277BD', '#00695C', '#2E7D32', '#558B2F',
    '#827717', '#E65100', '#4E342E', '#37474F', '#006064',
    '#880E4F', '#4A148C', '#1A237E', '#0D47A1', '#01579B',
    '#00838F', '#00796B', '#1B5E20', '#33691E', '#BF360C',
    '#546E7A', '#D81B60', '#7B1FA2', '#3949AB', '#0288D1',
    '#00ACC1', '#00897B', '#43A047', '#F4511E', '#F57F17',
    '#3E2723', '#B71C1C', '#4E342E', '#5E35B1', '#039BE5',
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _shift_earlier(t, minutes):
    total = max(t.hour * 60 + t.minute - minutes, 0)
    return time(total // 60, total % 60)

def _build_time_slots(start_time, end_time):
    """Build slot boundaries for a day. The first slot is LEAD_IN_MINUTES wide
    (the opening supervisor's window); every slot after that is SLOT_MINUTES wide."""
    slots = []
    current = start_time
    step = LEAD_IN_MINUTES
    while current < end_time:
        slots.append(current)
        total_minutes = current.hour * 60 + current.minute + step
        current = time(total_minutes // 60, total_minutes % 60)
        step = SLOT_MINUTES
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
    Checks DateOperatingHours first, falls back to weekly OperatingHours defaults.
    start_time is shifted LEAD_IN_MINUTES earlier to include the opening
    supervisor's lead-in window."""
    try:
        doh = DateOperatingHours.objects.get(date=d)
        if doh.is_closed:
            return None, None, True
        return _shift_earlier(doh.start_time, LEAD_IN_MINUTES), doh.end_time, False
    except DateOperatingHours.DoesNotExist:
        pass

    dow = _DOW_CODE.get(d.weekday())
    if dow:
        try:
            oh = OperatingHours.objects.get(day_of_week=dow)
            return _shift_earlier(oh.start_time, LEAD_IN_MINUTES), oh.end_time, False
        except OperatingHours.DoesNotExist:
            pass

    # System default if nothing configured
    return _shift_earlier(time(8, 0), LEAD_IN_MINUTES), time(17, 0), False

def _week_start(d):
    """Return Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())

def _total_availability_hours(avail_blocks):
    """Sum the duration (in hours) of an iterable of WeeklyAvailability-like blocks."""
    total_minutes = sum(
        (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
        for a in avail_blocks
    )
    return total_minutes / 60

def _is_scheduler_or_admin(user):
    return user.is_authenticated and (
        user.is_admin or user.scheduler_of.exists()
    )

def _is_admin(user):
    return user.is_authenticated and user.is_admin

# Used only for "Load Default Week": WeeklySchedule template blocks are
# dateless, but the grid-rendering code below expects ScheduleEntry-shaped
# objects with a concrete date. This wraps a template block with a real date
# for display, without writing anything to the database until the user saves.
_VirtualEntry = namedtuple(
    '_VirtualEntry', ['user', 'date', 'start_time', 'end_time', 'location', 'custom_label']
)

# ── availability ─────────────────────────────────────────────────────────────

@login_required
def manage_availability(request):
    days = [
        ('MON', 'Monday'), ('TUE', 'Tuesday'), ('WED', 'Wednesday'),
        ('THU', 'Thursday'), ('FRI', 'Friday'),
    ]
    can_edit = _can_edit_availability(request.user)
    operating_hours = {}
    for day_code, _ in days:
        oh, _ = OperatingHours.objects.get_or_create(
            day_of_week=day_code,
            defaults={'start_time': time(8, 0), 'end_time': time(18, 0)},
        )
        operating_hours[day_code] = {
            'start': _shift_earlier(oh.start_time, LEAD_IN_MINUTES),
            'end': oh.end_time,
        }

    all_starts = [operating_hours[day]['start'] for day, _ in days]
    all_ends = [operating_hours[day]['end'] for day, _ in days]
    grid_start = min(all_starts)
    grid_end = max(all_ends)
    slots = _build_time_slots(grid_start, grid_end)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, "Availability editing is currently closed.")
            return redirect('scheduling:manage_availability')
        preferences_form = EmployeePreferencesForm(request.POST, instance=request.user)
        if preferences_form.is_valid():
            preferences_form.save()

        # The submitted form has one AVAILABLE/PREFERRED/empty value per slot
        # checkbox, not per block, so the simplest correct update is to wipe
        # this employee's availability and rebuild it by run-length-encoding
        # contiguous same-type slots back into WeeklyAvailability blocks.
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
                end_total = last_slot.hour * 60 + last_slot.minute + SLOT_MINUTES
                end_time = time(end_total // 60, end_total % 60)
                WeeklyAvailability.objects.create(
                    user=request.user, day_of_week=day_code,
                    start_time=block_start, end_time=end_time,
                    availability_type=block_type,
                )

        return redirect('dashboard:dashboard')

    preferences_form = EmployeePreferencesForm(instance=request.user)

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

    total_availability_hours = _total_availability_hours(existing)
    window = AvailabilityWindow.current()

    context = {
        'grid': grid,
        'days': days,
        'start_hour': grid_start.hour,
        'end_hour': grid_end.hour,
        'preferences_form': preferences_form,
        'total_availability_hours': total_availability_hours,
        'min_availability_hours': MIN_AVAILABILITY_HOURS,
        'below_min_availability': total_availability_hours < MIN_AVAILABILITY_HOURS,
        'can_edit': can_edit,
        'availability_window': window,
        'has_override': request.user.has_availability_override(),
    }
    return render(request, 'scheduling/availability.html', context)

# ── operating hours (admin, calendar-aware) ───────────────────────────────────
@login_required
@user_passes_test(_is_admin)
def availability_window(request):
    window = AvailabilityWindow.current()
    if request.method == 'POST':
        form = AvailabilityWindowForm(request.POST, instance=window)
        if form.is_valid():
            form.save()
            messages.success(request, "Availability window updated.")
            return redirect('scheduling:availability_window')
    else:
        form = AvailabilityWindowForm(instance=window)
    return render(request, 'scheduling/availability_window.html', {'form': form, 'window': window})

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
    week_start = _week_start(parse_date(request.GET.get('week', '')) or today)
    week_dates = [week_start + timedelta(days=i) for i in range(5)]
    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    is_admin = request.user.is_admin
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

    # Assign unique colors within this schedule (by name order)
    employee_colors = {
        e.pk: EMPLOYEE_PALETTE[i % len(EMPLOYEE_PALETTE)]
        for i, e in enumerate(visible_employees)
    }

    # Desired weekly hours + lunch break preference, set by each employee on their availability page
    employee_desired_hours = {
        str(e.pk): e.desired_weekly_hours for e in visible_employees
    }
    employee_wants_lunch = {
        str(e.pk): e.wants_lunch_break for e in visible_employees
    }

    # Availability data for visible employees (keyed by emp pk → day → list of blocks)
    avail_data = {}
    avail_minutes_by_user = {}
    all_avail = WeeklyAvailability.objects.filter(user__in=visible_employees).order_by('start_time')
    for a in all_avail:
        avail_data.setdefault(str(a.user_id), {}).setdefault(a.day_of_week, []).append({
            'start': a.start_time.strftime('%H:%M'),
            'end': a.end_time.strftime('%H:%M'),
            'type': a.availability_type,
        })
        dur = (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
        avail_minutes_by_user[a.user_id] = avail_minutes_by_user.get(a.user_id, 0) + dur

    # Employees who haven't marked the minimum required availability — flagged
    # in the sidebar: 'none' (zero hours entered, red) is more urgent than
    # 'low' (some hours entered but still under the minimum, yellow).
    low_availability_flags = {}
    for e in visible_employees:
        hours = avail_minutes_by_user.get(e.pk, 0) / 60
        if hours <= 0:
            low_availability_flags[e.pk] = 'none'
        elif hours < MIN_AVAILABILITY_HOURS:
            low_availability_flags[e.pk] = 'low'

    dept_locs = ['']
    has_locs = False

    # Already-scheduled entries for visible employees on OTHER schedules this week
    # — used to show conflict overlay in JS
    if visible_employees:
        conflict_qs = ScheduleEntry.objects.filter(
            user__in=visible_employees, date__in=week_dates,
        ).exclude(schedule=active_schedule)
        conflict_data = {}
        for e in conflict_qs.select_related('user', 'schedule'):
            conflict_data.setdefault(str(e.user_id), []).append({
                'date': e.date.isoformat(),
                'start': e.start_time.strftime('%H:%M'),
                'end': e.end_time.strftime('%H:%M'),
                'schedule': e.schedule.name,
                'schedule_color': e.schedule.color,
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
    lead_in_slot_key = f"{slots[0].hour:02d}_{slots[0].minute:02d}" if slots else None

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
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup:
                        new_slots.setdefault(epk, set()).add(
                            (d.isoformat(), f"{slot.hour:02d}_{slot.minute:02d}")
                        )

        violations = []
        for epk, slot_set in new_slots.items():
            emp = emp_lookup[epk]
            if not emp.part_time:
                continue
            new_mins = sum(
                LEAD_IN_MINUTES if sk == lead_in_slot_key else SLOT_MINUTES
                for _, sk in slot_set
            )
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
                    f"{emp.first_name} {emp.last_name}: {total_hrs:.2f} hrs scheduled "
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
            per_emp = {}
            per_emp_labels = {}
            for slot in slots:
                sk = f"{slot.hour:02d}_{slot.minute:02d}"
                key = f"slot_{d.isoformat()}_{sk}"
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup:
                        per_emp.setdefault(epk, {})[slot] = epk
                        label = request.POST.get(f"{key}__label__{epk}", '')
                        per_emp_labels.setdefault(epk, {})[slot] = label
            for epk, emp_slots in per_emp.items():
                _slots_to_entries(emp_slots, slots, post_schedule, d, emp_lookup, request.user,
                                  slot_labels=per_emp_labels.get(epk, {}))

        messages.success(request, f"Schedule saved for {post_schedule}.")
        after_save = request.POST.get('redirect_after_save', '')
        redirect_url = after_save if after_save.startswith('?') else f"?week={week_start.isoformat()}&schedule={post_schedule_pk}"
        return redirect(f"{request.path}{redirect_url}")

    # ── GET: load existing entries (or the default template) into cell state ─
    load_default = request.GET.get('load_default') == '1'

    if load_default and active_schedule:
        dow_to_date = {_DOW_CODE.get(d.weekday()): d for d in week_dates}
        weekly_blocks = WeeklySchedule.objects.filter(
            schedule=active_schedule, user__in=visible_employees,
        ).select_related('user')
        entries = [
            _VirtualEntry(
                user=blk.user, date=dow_to_date[blk.day_of_week],
                start_time=blk.start_time, end_time=blk.end_time,
                location='', custom_label=blk.custom_label,
            )
            for blk in weekly_blocks if blk.day_of_week in dow_to_date
        ]
        if not entries:
            messages.info(request, f"No default weekly schedule is set for {active_schedule}.")
        else:
            messages.info(request, "Default weekly schedule loaded — review and click Save to apply.")
    else:
        entries_qs = ScheduleEntry.objects.filter(
            date__in=week_dates, schedule=active_schedule,
        ).select_related('user').order_by(
            'date', 'start_time', 'custom_label', 'user__last_name', 'user__first_name'
        ) if active_schedule else []
        entries = list(entries_qs)

    # cell_state[(date_iso, slot_key, loc_slug)] → list of {emp_pk, color}
    cell_state = {}
    for entry in entries:
        ls = _loc_slug(entry.location)
        color = employee_colors.get(entry.user.pk, '#999')
        for slot in slots:
            if entry.start_time <= slot < entry.end_time:
                sk = f"{slot.hour:02d}_{slot.minute:02d}"
                cell_state.setdefault((entry.date.isoformat(), sk, ls), []).append({
                    'emp_pk': str(entry.user.pk),
                    'color': color,
                    'label': entry.custom_label,
                })

    # Count distinct slots each label occupies per day (= total staffed time for that position)
    label_day_slots = {}
    for (date_iso, sk, ls), assignments in cell_state.items():
        for lbl in {a['label'] or '' for a in assignments}:
            key = (date_iso, lbl)
            label_day_slots[key] = label_day_slots.get(key, 0) + 1

    # Sort each cell: most-time label first, then alphabetically, then by emp_pk for stability
    for (date_iso, sk, ls), assignments in cell_state.items():
        assignments.sort(key=lambda a: (
            -label_day_slots.get((date_iso, a['label'] or ''), 0),
            a['label'] or '',
            a['emp_pk'],
        ))

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
            'date_num': str(d.day),
            'month_abbr': d.strftime('%b'),
            'is_today': d == today,
            'closed': day_hours[d]['closed'],
            'span': num_locs,
        })
        for loc in dept_locs:
            loc_header_cells.append({'loc': loc, 'date_iso': d.isoformat()})

    grid = []
    for idx, slot in enumerate(slots):
        sk = f"{slot.hour:02d}_{slot.minute:02d}"
        cells = []
        for d in week_dates:
            dh = day_hours[d]
            in_hours = not dh['closed'] and dh['start'] is not None and dh['start'] <= slot < dh['end']
            for loc in dept_locs:
                ls = _loc_slug(loc)
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
                    'assignments': cell_state.get((d.isoformat(), sk, ls), []),
                    'inp_name': inp_name,
                    'inp_id': inp_id,
                })
        grid.append({
            'time': slot, 'slot_key': sk,
            'display': _slot_display(slot),
            'show_label': slot.minute == 0 or idx == 0,
            'cells': cells,
        })

    # Position labels shared across the schedule
    schedule_labels_data = []
    if active_schedule:
        schedule_labels_data = list(
            ShiftLabel.objects.filter(schedule=active_schedule).values('pk', 'name', 'color')
        )

    employee_initials = {
        str(e.pk): (e.first_name[:1] + e.last_name[:1]).upper()
        for e in visible_employees
    }

    return render(request, 'scheduling/schedule_builder.html', {
        'week_start': week_start,
        'week_label': f"{week_start.strftime('%b')} {week_start.day} – {week_dates[-1].strftime('%b')} {week_dates[-1].day}, {week_dates[-1].year}",
        'prev_week': prev_week, 'next_week': next_week,
        'col_template': col_template,
        'num_locs': num_locs,
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
        'employee_desired_hours_json': json.dumps(employee_desired_hours),
        'employee_wants_lunch_json': json.dumps(employee_wants_lunch),
        'low_availability_flags': low_availability_flags,
        'min_availability_hours': MIN_AVAILABILITY_HOURS,
        'schedule_labels_json': json.dumps(schedule_labels_data),
        'employee_initials_json': json.dumps(employee_initials),
        'is_admin': is_admin, 'today': today,
        'load_default': load_default,
    })


DEFAULT_BUILDER_DAYS = [d for d in DayOfWeek.choices]  # [('MON', 'Monday'), ...]


def _default_day_hours():
    """Weekly operating-hours span for each weekday, falling back to 8–5 if unconfigured.
    Start times are shifted LEAD_IN_MINUTES earlier for the opening supervisor's window."""
    oh_by_day = {oh.day_of_week: oh for oh in OperatingHours.objects.all()}
    day_hours = {}
    for day_code, _label in DEFAULT_BUILDER_DAYS:
        oh = oh_by_day.get(day_code)
        start, end = (oh.start_time, oh.end_time) if oh else (time(8, 0), time(17, 0))
        day_hours[day_code] = (_shift_earlier(start, LEAD_IN_MINUTES), end)
    return day_hours


@login_required
@user_passes_test(_is_scheduler_or_admin)
def default_schedule_builder(request):
    """Schedulers define a recurring default week (day-of-week based) per Schedule.
    Saved as WeeklySchedule rows; the live schedule_builder can load these to prefill a real week."""
    from account.models import Employee

    is_admin = request.user.is_admin
    if is_admin:
        allowed_schedules = list(Schedule.objects.all().order_by('name'))
    else:
        allowed_schedules = list(request.user.scheduler_of.all().order_by('name'))

    schedule_pk_param = (
        request.POST.get('active_schedule_pk')
        or request.GET.get('schedule')
        or (str(allowed_schedules[0].pk) if allowed_schedules else '')
    )
    active_schedule = next((s for s in allowed_schedules if str(s.pk) == schedule_pk_param), None)
    if not active_schedule and allowed_schedules:
        active_schedule = allowed_schedules[0]
        schedule_pk_param = str(active_schedule.pk)

    if active_schedule:
        visible_employees = list(
            Employee.objects.filter(member_of=active_schedule)
            .distinct().order_by('last_name', 'first_name')
        )
    else:
        visible_employees = []

    employee_colors = {
        e.pk: EMPLOYEE_PALETTE[i % len(EMPLOYEE_PALETTE)]
        for i, e in enumerate(visible_employees)
    }

    employee_desired_hours = {
        str(e.pk): e.desired_weekly_hours for e in visible_employees
    }
    employee_wants_lunch = {
        str(e.pk): e.wants_lunch_break for e in visible_employees
    }

    # Availability is already day-of-week based — same shape as the live builder uses.
    avail_data = {}
    avail_minutes_by_user = {}
    if visible_employees:
        all_avail = WeeklyAvailability.objects.filter(user__in=visible_employees).order_by('start_time')
        for a in all_avail:
            avail_data.setdefault(str(a.user_id), {}).setdefault(a.day_of_week, []).append({
                'start': a.start_time.strftime('%H:%M'),
                'end': a.end_time.strftime('%H:%M'),
                'type': a.availability_type,
            })
            dur = (a.end_time.hour * 60 + a.end_time.minute) - (a.start_time.hour * 60 + a.start_time.minute)
            avail_minutes_by_user[a.user_id] = avail_minutes_by_user.get(a.user_id, 0) + dur

    # Employees who haven't marked the minimum required availability — flagged
    # in the sidebar: 'none' (zero hours entered, red) is more urgent than
    # 'low' (some hours entered but still under the minimum, yellow).
    low_availability_flags = {}
    for e in visible_employees:
        hours = avail_minutes_by_user.get(e.pk, 0) / 60
        if hours <= 0:
            low_availability_flags[e.pk] = 'none'
        elif hours < MIN_AVAILABILITY_HOURS:
            low_availability_flags[e.pk] = 'low'

    # Conflicts = this employee's default hours on OTHER schedules (keyed by day code,
    # reusing the 'date' key so the existing conflict-matching JS works unmodified).
    conflict_data = {}
    other_default_qs = WeeklySchedule.objects.none()
    if visible_employees:
        other_default_qs = WeeklySchedule.objects.filter(
            user__in=visible_employees,
        ).exclude(schedule=active_schedule)
        for blk in other_default_qs.select_related('user', 'schedule'):
            conflict_data.setdefault(str(blk.user_id), []).append({
                'date': blk.day_of_week,
                'start': blk.start_time.strftime('%H:%M'),
                'end': blk.end_time.strftime('%H:%M'),
                'schedule': blk.schedule.name,
                'schedule_color': blk.schedule.color,
            })

    # Part-time flag + default hours already committed on other schedules
    parttime_flags = {}
    other_hours_map = {}
    for emp in visible_employees:
        is_pt = emp.part_time
        parttime_flags[emp.pk] = is_pt
        if is_pt:
            total_mins = sum(
                (blk.end_time.hour * 60 + blk.end_time.minute)
                - (blk.start_time.hour * 60 + blk.start_time.minute)
                for blk in other_default_qs.filter(user=emp)
            )
            other_hours_map[emp.pk] = round(total_mins / 60, 2)
        else:
            other_hours_map[emp.pk] = 0

    day_hours = _default_day_hours()
    grid_start = min(h[0] for h in day_hours.values())
    grid_end = max(h[1] for h in day_hours.values())
    slots = _build_time_slots(grid_start, grid_end)
    lead_in_slot_key = f"{slots[0].hour:02d}_{slots[0].minute:02d}" if slots else None

    # date→day map, keyed by day code onto itself, so the shared JS's
    # `dateDayMap[dateStr]` lookup works unmodified against day codes.
    date_day_map = {code: code for code, _label in DEFAULT_BUILDER_DAYS}

    # ── POST: rebuild the default week for this schedule ─────────────────────
    if request.method == 'POST':
        post_schedule_pk = request.POST.get('active_schedule_pk', schedule_pk_param)
        post_schedule = next((s for s in allowed_schedules if str(s.pk) == post_schedule_pk), active_schedule)
        if not post_schedule:
            messages.error(request, "Select a schedule first.")
            return redirect('scheduling:default_schedule_builder')

        post_emps = list(Employee.objects.filter(member_of=post_schedule).distinct())
        emp_lookup = {str(e.pk): e for e in post_emps}

        # ── Part-time hour-limit check (before any DB changes) ────────────────
        new_slots = {}
        for day_code, _label in DEFAULT_BUILDER_DAYS:
            dh_start, dh_end = day_hours[day_code]
            for slot in slots:
                if not (dh_start <= slot < dh_end):
                    continue
                key = f"slot_{day_code}_{slot.hour:02d}_{slot.minute:02d}"
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup:
                        new_slots.setdefault(epk, set()).add((day_code, f"{slot.hour:02d}_{slot.minute:02d}"))

        violations = []
        for epk, slot_set in new_slots.items():
            emp = emp_lookup[epk]
            if not emp.part_time:
                continue
            new_mins = sum(
                LEAD_IN_MINUTES if sk == lead_in_slot_key else SLOT_MINUTES
                for _, sk in slot_set
            )
            other_mins = sum(
                (blk.end_time.hour * 60 + blk.end_time.minute)
                - (blk.start_time.hour * 60 + blk.start_time.minute)
                for blk in WeeklySchedule.objects.filter(user=emp).exclude(schedule=post_schedule)
            )
            total_hrs = (new_mins + other_mins) / 60
            if total_hrs > PARTTIME_WEEKLY_MAX:
                violations.append(
                    f"{emp.first_name} {emp.last_name}: {total_hrs:.2f} hrs scheduled "
                    f"(limit {PARTTIME_WEEKLY_MAX})"
                )

        if violations:
            for v in violations:
                messages.error(request, f"Over weekly limit — {v}")
            return redirect(f"{request.path}?schedule={post_schedule_pk}")

        WeeklySchedule.objects.filter(schedule=post_schedule).delete()

        for day_code, _label in DEFAULT_BUILDER_DAYS:
            dh_start, dh_end = day_hours[day_code]
            per_emp = {}
            per_emp_labels = {}
            for slot in slots:
                if not (dh_start <= slot < dh_end):
                    continue
                sk = f"{slot.hour:02d}_{slot.minute:02d}"
                key = f"slot_{day_code}_{sk}"
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup:
                        per_emp.setdefault(epk, {})[slot] = epk
                        label = request.POST.get(f"{key}__label__{epk}", '')
                        per_emp_labels.setdefault(epk, {})[slot] = label
            for epk, emp_slots in per_emp.items():
                _slots_to_weekly_blocks(emp_slots, post_schedule, day_code, emp_lookup,
                                         slot_labels=per_emp_labels.get(epk, {}), all_slots=slots)

        messages.success(request, f"Default weekly schedule saved for {post_schedule}.")
        return redirect(f"{request.path}?schedule={post_schedule_pk}")

    # ── GET: load existing WeeklySchedule blocks into cell state ─────────────
    blocks = list(
        WeeklySchedule.objects.filter(schedule=active_schedule).select_related('user')
    ) if active_schedule else []

    cell_state = {}
    for blk in blocks:
        color = employee_colors.get(blk.user.pk, '#999')
        for slot in slots:
            if blk.start_time <= slot < blk.end_time:
                sk = f"{slot.hour:02d}_{slot.minute:02d}"
                cell_state.setdefault((blk.day_of_week, sk), []).append({
                    'emp_pk': str(blk.user.pk),
                    'color': color,
                    'label': blk.custom_label,
                })

    label_day_slots = {}
    for (day_code, sk), assignments in cell_state.items():
        for lbl in {a['label'] or '' for a in assignments}:
            key = (day_code, lbl)
            label_day_slots[key] = label_day_slots.get(key, 0) + 1

    for (day_code, sk), assignments in cell_state.items():
        assignments.sort(key=lambda a: (
            -label_day_slots.get((day_code, a['label'] or ''), 0),
            a['label'] or '',
            a['emp_pk'],
        ))

    col_template = f"72px repeat({len(DEFAULT_BUILDER_DAYS)}, 1fr)"
    day_header_cols = [{'code': code, 'label': label} for code, label in DEFAULT_BUILDER_DAYS]

    grid = []
    for idx, slot in enumerate(slots):
        sk = f"{slot.hour:02d}_{slot.minute:02d}"
        cells = []
        for day_code, _label in DEFAULT_BUILDER_DAYS:
            dh_start, dh_end = day_hours[day_code]
            in_hours = dh_start <= slot < dh_end
            inp_name = f"slot_{day_code}_{sk}"
            cells.append({
                'day_code': day_code,
                'in_hours': in_hours,
                'assignments': cell_state.get((day_code, sk), []),
                'inp_name': inp_name,
                'inp_id': f"inp_{day_code}_{sk}",
            })
        grid.append({
            'time': slot, 'slot_key': sk,
            'display': _slot_display(slot),
            'show_label': slot.minute == 0 or idx == 0,
            'cells': cells,
        })

    schedule_labels_data = []
    if active_schedule:
        schedule_labels_data = list(
            ShiftLabel.objects.filter(schedule=active_schedule).values('pk', 'name', 'color')
        )

    employee_initials = {
        str(e.pk): (e.first_name[:1] + e.last_name[:1]).upper()
        for e in visible_employees
    }

    return render(request, 'scheduling/default_schedule_builder.html', {
        'col_template': col_template,
        'day_header_cols': day_header_cols,
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
        'employee_desired_hours_json': json.dumps(employee_desired_hours),
        'employee_wants_lunch_json': json.dumps(employee_wants_lunch),
        'low_availability_flags': low_availability_flags,
        'min_availability_hours': MIN_AVAILABILITY_HOURS,
        'schedule_labels_json': json.dumps(schedule_labels_data),
        'employee_initials_json': json.dumps(employee_initials),
        'is_admin': is_admin,
    })


@login_required
@user_passes_test(_is_scheduler_or_admin)
@require_http_methods(['GET', 'POST'])
def schedule_labels(request, schedule_pk):
    """GET: list position labels for a schedule. POST: create a new label."""
    schedule = get_object_or_404(Schedule, pk=schedule_pk)

    if request.method == 'GET':
        labels = ShiftLabel.objects.filter(schedule=schedule)
        return JsonResponse({'labels': [{'pk': l.pk, 'name': l.name, 'color': l.color} for l in labels]})

    data = json.loads(request.body)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    existing_colors = set(ShiftLabel.objects.filter(schedule=schedule).values_list('color', flat=True))
    color = next((c for c in LABEL_PALETTE if c not in existing_colors), LABEL_PALETTE[0])

    label, created = ShiftLabel.objects.get_or_create(
        schedule=schedule, name=name,
        defaults={'color': color}
    )
    if not created:
        return JsonResponse({'error': 'Label already exists'}, status=409)
    return JsonResponse({'pk': label.pk, 'name': label.name, 'color': label.color}, status=201)


@login_required
@user_passes_test(_is_scheduler_or_admin)
@require_http_methods(['DELETE'])
def delete_shift_label(request, label_pk):
    """DELETE: remove a position label."""
    label = get_object_or_404(ShiftLabel, pk=label_pk)
    label.delete()
    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_is_scheduler_or_admin)
@require_http_methods(['POST'])
def save_schedule_day(request):
    """Save/rebuild schedule entries for a single day. Called via AJAX."""
    from account.models import Employee

    schedule_pk = request.POST.get('schedule_pk', '')
    date_iso = request.POST.get('date_iso', '')

    try:
        target_date = date.fromisoformat(date_iso)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date'}, status=400)

    schedule = get_object_or_404(Schedule, pk=schedule_pk)
    if not (request.user.is_admin or schedule in request.user.scheduler_of.all()):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    dh_start, dh_end, closed = _get_operating_hours_for_date(target_date)
    if closed or not dh_start:
        ScheduleEntry.objects.filter(date=target_date, schedule=schedule).delete()
        return JsonResponse({'ok': True})

    slots = _build_time_slots(dh_start, dh_end)
    emp_lookup = {str(e.pk): e for e in Employee.objects.filter(member_of=schedule)}

    ScheduleEntry.objects.filter(date=target_date, schedule=schedule).delete()

    per_emp = {}
    per_emp_labels = {}
    for slot in slots:
        sk = f"{slot.hour:02d}_{slot.minute:02d}"
        key = f"slot_{date_iso}_{sk}"
        for epk in request.POST.getlist(key):
            if epk in emp_lookup:
                per_emp.setdefault(epk, {})[slot] = epk
                label = request.POST.get(f"{key}__label__{epk}", '')
                per_emp_labels.setdefault(epk, {})[slot] = label

    for epk, emp_slots in per_emp.items():
        _slots_to_entries(emp_slots, slots, schedule, target_date, emp_lookup, request.user,
                          slot_labels=per_emp_labels.get(epk, {}))

    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_is_scheduler_or_admin)
@require_http_methods(['POST'])
def save_week_as_default(request):
    """Persist the schedule builder's currently-displayed week as the schedule's
    new default weekly template, replacing whatever default previously existed."""
    from account.models import Employee

    schedule_pk = request.POST.get('active_schedule_pk', '')
    week_start = parse_date(request.POST.get('week_start', ''))
    if not week_start:
        return JsonResponse({'error': 'Invalid week'}, status=400)

    schedule = get_object_or_404(Schedule, pk=schedule_pk)
    if not (request.user.is_admin or schedule in request.user.scheduler_of.all()):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    week_dates = [week_start + timedelta(days=i) for i in range(5)]
    emp_lookup = {str(e.pk): e for e in Employee.objects.filter(member_of=schedule).distinct()}

    WeeklySchedule.objects.filter(schedule=schedule).delete()

    for d in week_dates:
        day_code = _DOW_CODE.get(d.weekday())
        if not day_code:
            continue
        dh_start, dh_end, closed = _get_operating_hours_for_date(d)
        if closed or not dh_start:
            continue
        day_slots = _build_time_slots(dh_start, dh_end)
        per_emp = {}
        per_emp_labels = {}
        for slot in day_slots:
            sk = f"{slot.hour:02d}_{slot.minute:02d}"
            key = f"slot_{d.isoformat()}_{sk}"
            for epk in request.POST.getlist(key):
                if epk in emp_lookup:
                    per_emp.setdefault(epk, {})[slot] = epk
                    label = request.POST.get(f"{key}__label__{epk}", '')
                    per_emp_labels.setdefault(epk, {})[slot] = label
        for epk, emp_slots in per_emp.items():
            _slots_to_weekly_blocks(emp_slots, schedule, day_code, emp_lookup,
                                     slot_labels=per_emp_labels.get(epk, {}), all_slots=day_slots)

    messages.success(request, f"This week's schedule is now the default for {schedule}.")
    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_is_scheduler_or_admin)
def export_teams_shifts(request):
    if request.user.is_admin:
        schedules = Schedule.objects.order_by('name')
    else:
        schedules = request.user.scheduler_of.order_by('name')

    if request.method == 'POST':
        from django.http import HttpResponse
        from .exports import build_teams_shifts_xlsx

        date_from = parse_date(request.POST.get('date_from', ''))
        date_to = parse_date(request.POST.get('date_to', ''))
        allowed_pks = set(schedules.values_list('pk', flat=True))
        schedule_pks = [p for p in request.POST.getlist('schedules') if int(p) in allowed_pks]

        if not date_from or not date_to or date_from > date_to:
            messages.error(request, "Please select a valid date range.")
            return redirect('scheduling:export_teams_shifts')
        if not schedule_pks:
            schedule_pks = list(allowed_pks)

        # Part-time employees are no longer blocked from being over-scheduled
        # while drawing (their sidebar pill just flags fuchsia instead) — the
        # weekly cap is enforced here instead, at the point the schedule
        # actually leaves the building. Checked per calendar week across ALL
        # of the employee's schedules, not just the ones being exported,
        # since the cap is a total-hours-per-week limit, not a per-schedule one.
        from account.models import Employee
        parttime_pks = set(
            Employee.objects.filter(part_time=True, is_active=True).values_list('pk', flat=True)
        )
        overages = []
        if parttime_pks:
            week_cursor = _week_start(date_from)
            last_week_start = _week_start(date_to)
            while week_cursor <= last_week_start:
                week_end = week_cursor + timedelta(days=6)
                hours_by_emp = {}
                week_entries = ScheduleEntry.objects.filter(
                    date__gte=week_cursor, date__lte=week_end, user_id__in=parttime_pks,
                ).select_related('user')
                for entry in week_entries:
                    dur_minutes = (
                        (entry.end_time.hour * 60 + entry.end_time.minute)
                        - (entry.start_time.hour * 60 + entry.start_time.minute)
                    )
                    info = hours_by_emp.setdefault(entry.user_id, {'hours': 0.0, 'name': entry.user.get_full_name()})
                    info['hours'] += dur_minutes / 60
                for info in hours_by_emp.values():
                    if info['hours'] > PARTTIME_WEEKLY_MAX:
                        overages.append(
                            f"{info['name']}: {info['hours']:.2f} hrs the week of {week_cursor.strftime('%b %d, %Y')} "
                            f"(limit {PARTTIME_WEEKLY_MAX} hrs)"
                        )
                week_cursor += timedelta(weeks=1)

        if overages:
            messages.error(
                request,
                "Cannot export — the following part-time employees are over the weekly hour cap: "
                + "; ".join(overages)
            )
            return redirect('scheduling:export_teams_shifts')

        xlsx_bytes = build_teams_shifts_xlsx(schedule_pks, date_from, date_to)
        filename = f"TeamsShifts_{date_from}_{date_to}.xlsx"
        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'scheduling/export_teams_shifts.html', {'schedules': schedules})


def _slot_width(slot_time, lead_in_time):
    """A slot is LEAD_IN_MINUTES wide if it's the day's opening-supervisor lead-in
    slot, otherwise SLOT_MINUTES wide."""
    return LEAD_IN_MINUTES if lead_in_time is not None and slot_time == lead_in_time else SLOT_MINUTES


def _slots_to_blocks(emp_slots, slot_labels=None, lead_in_time=None):
    """Convert a {slot: emp_pk_str} mapping into per-employee contiguous
    (start_time, end_time, label) blocks, splitting on gaps or label changes."""
    by_emp = {}
    for slot, epk in emp_slots.items():
        by_emp.setdefault(epk, []).append(slot)

    result = {}
    for epk, slot_list in by_emp.items():
        slot_list.sort()
        blocks = []
        block_start = None
        block_label = ''
        prev_slot = None
        for slot in slot_list:
            if block_start is None:
                block_start = slot
                block_label = (slot_labels or {}).get(slot, '')
            elif prev_slot is not None:
                width = _slot_width(prev_slot, lead_in_time)
                expected = time(
                    (prev_slot.hour * 60 + prev_slot.minute + width) // 60,
                    (prev_slot.hour * 60 + prev_slot.minute + width) % 60,
                )
                current_label = (slot_labels or {}).get(slot, '')
                if slot != expected or current_label != block_label:
                    blocks.append((block_start, expected, block_label))
                    block_start = slot
                    block_label = current_label
            prev_slot = slot

        if block_start is not None and prev_slot is not None:
            width = _slot_width(prev_slot, lead_in_time)
            end_t = time(
                (prev_slot.hour * 60 + prev_slot.minute + width) // 60,
                (prev_slot.hour * 60 + prev_slot.minute + width) % 60,
            )
            if block_start < end_t:
                blocks.append((block_start, end_t, block_label))
        result[epk] = blocks
    return result


def _slots_to_entries(emp_slots, all_slots, schedule, d, emp_lookup, created_by, slot_labels=None):
    """Convert a {slot: emp_pk_str} mapping into contiguous ScheduleEntry objects."""
    lead_in_time = all_slots[0] if all_slots else None
    for epk, blocks in _slots_to_blocks(emp_slots, slot_labels, lead_in_time).items():
        emp = emp_lookup[epk]
        for start_t, end_t, label in blocks:
            ScheduleEntry.objects.create(
                user=emp, schedule=schedule,
                date=d, start_time=start_t, end_time=end_t,
                created_by=created_by,
                custom_label=label,
            )


def _slots_to_weekly_blocks(emp_slots, schedule, day_code, emp_lookup, slot_labels=None, all_slots=None):
    """Convert a {slot: emp_pk_str} mapping into contiguous WeeklySchedule objects for one day-of-week."""
    lead_in_time = all_slots[0] if all_slots else None
    for epk, blocks in _slots_to_blocks(emp_slots, slot_labels, lead_in_time).items():
        emp = emp_lookup[epk]
        for start_t, end_t, label in blocks:
            WeeklySchedule.objects.create(
                user=emp, schedule=schedule, day_of_week=day_code,
                start_time=start_t, end_time=end_t,
                custom_label=label,
            )

def _can_edit_availability(user):
    """Admins and employees with an active per-user override bypass the
    global AvailabilityWindow entirely; everyone else is subject to it."""
    if not user.is_authenticated:
        return False
    if user.is_admin or user.has_availability_override():
        return True
    return AvailabilityWindow.current().is_currently_open()