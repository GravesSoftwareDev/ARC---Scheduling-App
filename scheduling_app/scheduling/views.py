from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.dateparse import parse_date
from datetime import time, date, timedelta
from collections import namedtuple
import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import WeeklyAvailability, OperatingHours, DayOfWeek, ScheduleEntry, DateOperatingHours, Schedule, ShiftLabel, LABEL_PALETTE, WeeklySchedule, AvailabilityWindow, EmployeeColor, hex_color_validator, Term, TERM_ORDER, term_for_date, term_label
from django.core.exceptions import ValidationError
from .forms import WeeklyHoursForm, DateOperatingHoursForm, EmployeePreferencesForm, AvailabilityWindowForm
from . import hours


PARTTIME_WEEKLY_MAX = 19.5  # hours — applies to all part-time employees
DEFAULT_TERM_COOKIE = 'default_term'  # schedule builder's last-picked default-week semester, e.g. "SP-2027"
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

def _employee_colors(schedule, employees):
    """({emp_pk: color}, {pks with a saved color}) for `employees` (in name
    order) on `schedule`. Saved EmployeeColor rows win; everyone else gets
    EMPLOYEE_PALETTE by position, as before colors were editable."""
    saved = dict(
        EmployeeColor.objects.filter(schedule=schedule, user__in=employees)
        .values_list('user_id', 'color')
    ) if schedule else {}
    colors = {
        e.pk: saved.get(e.pk, EMPLOYEE_PALETTE[i % len(EMPLOYEE_PALETTE)])
        for i, e in enumerate(employees)
    }
    return colors, set(saved)

def _slot_key(t):
    return f"{t.hour:02d}_{t.minute:02d}"

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

_DOW_CODE = hours.DOW_CODE

def _roles_of(employees):
    """Distinct roles among `employees` — or just the default ('') if there
    are none, so an empty schedule still shows the default hours."""
    return sorted({e.role or '' for e in employees}) or ['']

def _minutes(t):
    return t.hour * 60 + t.minute

# Row layout for a builder grid — see _RoleHours.grid().
#   day_hours: {day_key: (start, end, is_closed)} spanning every member role
#   slots:     row start times; end: when the last row ends
#   slot_ends: {row start: row end} (rows are 30 min, or 15 at quarter-hour edges)
_Grid = namedtuple('_Grid', ['day_hours', 'slots', 'end', 'slot_ends'])

class _RoleHours:
    """Memoized (role, day) → (start, end, is_closed) lookups for the schedule
    builders, where the grid spans every member role's hours but each
    employee may only be scheduled inside their own role's hours. `resolve`
    is called as resolve(role, day_key); day_key is a date (live builder) or
    a day code (default-week builder)."""

    def __init__(self, resolve):
        self._resolve = resolve
        self._cache = {}

    def span(self, role, day_key):
        key = (role or '', day_key)
        if key not in self._cache:
            self._cache[key] = self._resolve(role or '', day_key)
        return self._cache[key]

    def combined(self, roles, day_key):
        return hours.combine_spans([self.span(r, day_key) for r in roles])

    def covers(self, role, day_key, slot):
        start, end, closed = self.span(role, day_key)
        return not closed and start <= slot < end

    def grid(self, roles, day_keys):
        """The row layout for a grid over `day_keys`: it spans every role's
        hours, with short rows at each role's quarter-hour open/close times.
        The page and every save path call this with the same roles and days
        so posted slot keys always match the rendered rows."""
        day_hours = {k: self.combined(roles, k) for k in day_keys}
        open_days = [(s, e) for s, e, closed in day_hours.values() if not closed]
        if open_days:
            start, end = min(s for s, _ in open_days), max(e for _, e in open_days)
        else:
            start, end = hours.DEFAULT_OPEN, hours.DEFAULT_CLOSE
        edges = hours.span_edges(self.span(r, k) for r in roles for k in day_keys)
        slots = hours.build_slots(start, end, edges)
        return _Grid(day_hours, slots, end, hours.slot_ends(slots, end))

    def as_json(self, employees, day_keys, key_str=str):
        """{emp_pk: {day: [open_min, close_min] or None if closed}} for the builder JS."""
        out = {}
        for e in employees:
            per_day = {}
            for k in day_keys:
                start, end, closed = self.span(e.role, k)
                per_day[key_str(k)] = None if closed else [_minutes(start), _minutes(end)]
            out[str(e.pk)] = per_day
        return json.dumps(out)


def _live_role_hours():
    """_RoleHours keyed by date, for the live (dated) schedule builder."""
    return _RoleHours(lambda role, d: hours.hours_for_date(d, role))


def _grid_slots_json(grid):
    """[[slot_key, minutes], ...] in row order — the builder JS uses it to find
    neighbouring rows and to count hours, since rows aren't all 30 minutes."""
    return json.dumps([
        [_slot_key(s), _minutes(grid.slot_ends[s]) - _minutes(s)] for s in grid.slots
    ])

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

def _requested_term(params, today):
    """(term, year) from a request's `term`/`year` params, falling back to the
    semester `today` is in for anything missing or invalid."""
    term = params.get('term', '')
    if term not in Term.values:
        term = term_for_date(today)
    try:
        year = int(params.get('year', ''))
    except ValueError:
        year = today.year
    if not 2000 <= year <= 2100:
        year = today.year
    return term, year

def _newest_terms_first(pairs):
    """Sort (term, year) pairs newest semester first."""
    return sorted(pairs, key=lambda p: (p[1], TERM_ORDER[p[0]]), reverse=True)

def _saved_terms(schedule):
    """[(term, year), ...] that have a saved default week on `schedule`, newest first."""
    if not schedule:
        return []
    return _newest_terms_first(set(
        WeeklySchedule.objects.filter(schedule=schedule).values_list('term', 'year')
    ))

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
    # The grid covers this employee's own role's weekly hours.
    role_weekly = hours.weekly_hours(request.user.role)
    operating_hours = {
        day_code: {'start': role_weekly[day_code][0], 'end': role_weekly[day_code][1]}
        for day_code, _ in days
    }

    grid_start = min(oh['start'] for oh in operating_hours.values())
    grid_end = max(oh['end'] for oh in operating_hours.values())
    edges = {t for oh in operating_hours.values() for t in (oh['start'], oh['end'])}
    slots = hours.build_slots(grid_start, grid_end, edges)

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
                WeeklyAvailability.objects.create(
                    user=request.user, day_of_week=day_code,
                    start_time=block_start, end_time=grid_end,
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
    """Weekly hours, edited for one role at a time via the role dropdown
    ('' = Default, which every role uses until its own hours are saved).
    A role's form starts from whatever hours it currently resolves to."""
    from account.models import Employee

    role_labels = dict(Employee.Role.choices)
    role = request.POST.get('role', request.GET.get('role', ''))
    if role not in role_labels:
        role = ''
    role_url = f"{request.path}?role={role}" if role else request.path

    for day_code, _label in DayOfWeek.choices:
        OperatingHours.objects.get_or_create(
            role='', day_of_week=day_code,
            defaults={'start_time': hours.DEFAULT_OPEN, 'end_time': hours.DEFAULT_CLOSE}
        )

    if request.method == 'POST' and role and 'reset_role' in request.POST:
        OperatingHours.objects.filter(role=role).delete()
        messages.success(request, f"{role_labels[role]} now uses the default hours.")
        return redirect(role_url)

    current = hours.weekly_hours(role)
    hours_form = WeeklyHoursForm(initial_hours=current)
    date_form = DateOperatingHoursForm()

    if request.method == 'POST' and 'save_hours' in request.POST:
        hours_form = WeeklyHoursForm(request.POST, initial_hours=current)
        if hours_form.is_valid():
            new_hours = hours_form.hours()
            if role and new_hours == hours.weekly_hours(''):
                # Identical to the defaults — keep following them instead of
                # pinning a copy that would go stale when the defaults change.
                OperatingHours.objects.filter(role=role).delete()
                messages.success(request, f"{role_labels[role]} hours match the defaults, so it now uses the default hours.")
            else:
                for day_code, (start, end) in new_hours.items():
                    OperatingHours.objects.update_or_create(
                        role=role, day_of_week=day_code,
                        defaults={'start_time': start, 'end_time': end},
                    )
                who = role_labels[role] if role else "Default"
                messages.success(request, f"{who} operating hours updated.")
            return redirect(role_url)
    elif request.method == 'POST' and 'add_special' in request.POST:
        date_form = DateOperatingHoursForm(request.POST)
        if date_form.is_valid():
            date_form.save()
            messages.success(request, "Special date hours added.")
            return redirect(role_url)

    customized_roles = set(
        OperatingHours.objects.exclude(role='').values_list('role', flat=True)
    )
    role_options = [{'code': '', 'label': 'Default'}] + [
        {'code': code, 'label': label + (' (custom hours)' if code in customized_roles else '')}
        for code, label in Employee.Role.choices
    ]

    # Upcoming special date overrides
    today = date.today()
    special_hours = DateOperatingHours.objects.filter(date__gte=today).order_by('date')[:30]

    return render(request, 'scheduling/operating_hours.html', {
        'hours_form': hours_form,
        'date_form': date_form,
        'special_hours': special_hours,
        'role_options': role_options,
        'active_role': role,
        'active_role_label': role_labels.get(role, 'Default'),
        'role_customized': role in customized_roles,
    })

@login_required
@user_passes_test(_is_admin)
def delete_special_hours(request, pk):
    entry = get_object_or_404(DateOperatingHours, pk=pk)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Special date removed.")
    role = request.POST.get('role', '')
    url = reverse('scheduling:operating_hours')
    return redirect(f"{url}?role={role}" if role else url)

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

    employee_colors, custom_color_pks = _employee_colors(active_schedule, visible_employees)

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

    # Employees who haven't marked the minimum required availability — flagged red in the sidebar
    low_availability_flags = {
        e.pk: (avail_minutes_by_user.get(e.pk, 0) / 60) < MIN_AVAILABILITY_HOURS
        for e in visible_employees
    }

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

    # Operating hours per day: the grid spans every member role's hours, and
    # each employee is limited to their own role's hours (role_hours.covers).
    role_hours = _live_role_hours()
    week_grid = role_hours.grid(_roles_of(visible_employees), week_dates)
    day_hours = {
        d: {'start': start, 'end': end, 'closed': closed}
        for d, (start, end, closed) in week_grid.day_hours.items()
    }
    slots = week_grid.slots
    slot_minutes = hours.slot_minutes(slots, week_grid.end)

    # ── POST: rebuild schedule for this schedule/week ────────────────────────
    if request.method == 'POST':
        post_schedule_pk = request.POST.get('active_schedule_pk', schedule_pk_param)
        post_schedule = next((s for s in allowed_schedules if str(s.pk) == post_schedule_pk), active_schedule)
        post_emps = list(
            Employee.objects.filter(member_of=post_schedule).distinct()
        ) if post_schedule else []
        emp_lookup = {str(e.pk): e for e in post_emps}

        # ── Part-time hour-limit check (before any DB changes) ────────────────
        new_slots = {}   # emp_pk_str → set of (date, slot)
        for d in week_dates:
            dh = day_hours[d]
            if dh['closed'] or not dh['start']:
                continue
            for slot in slots:
                key = f"slot_{d.isoformat()}_{_slot_key(slot)}"
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup and role_hours.covers(emp_lookup[epk].role, d, slot):
                        new_slots.setdefault(epk, set()).add((d, slot))

        violations = []
        for epk, slot_set in new_slots.items():
            emp = emp_lookup[epk]
            if not emp.part_time:
                continue
            new_mins = sum(slot_minutes[slot] for _, slot in slot_set)
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

        outside_role_hours = set()  # names of employees with slots dropped below
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
                    if epk not in emp_lookup:
                        continue
                    if not role_hours.covers(emp_lookup[epk].role, d, slot):
                        outside_role_hours.add(emp_lookup[epk].get_full_name())
                        continue
                    per_emp.setdefault(epk, {})[slot] = epk
                    label = request.POST.get(f"{key}__label__{epk}", '')
                    per_emp_labels.setdefault(epk, {})[slot] = label
            for epk, emp_slots in per_emp.items():
                _slots_to_entries(emp_slots, week_grid.slot_ends, post_schedule, d, emp_lookup, request.user,
                                  slot_labels=per_emp_labels.get(epk, {}))

        if outside_role_hours:
            messages.warning(
                request,
                "Some time was not saved because it falls outside the employee's role hours: "
                + ", ".join(sorted(outside_role_hours)),
            )
        messages.success(request, f"Schedule saved for {post_schedule}.")
        after_save = request.POST.get('redirect_after_save', '')
        redirect_url = after_save if after_save.startswith('?') else f"?week={week_start.isoformat()}&schedule={post_schedule_pk}"
        return redirect(f"{request.path}{redirect_url}")

    # ── GET: load existing entries (or the default template) into cell state ─
    load_default = request.GET.get('load_default') == '1'
    # The Default Week dropdown picks the semester that both "Load Default
    # Week" and "Save Week as Default" use. It offers every saved default plus
    # the current semester (even before it has one), and preselects the
    # semester in the URL (just loaded or saved), else the scheduler's last
    # pick (the DEFAULT_TERM_COOKIE the page's JS sets on every change, so it
    # survives week/schedule navigation), else the current semester.
    current_term = (term_for_date(today), today.year)
    if 'term' in request.GET:
        term_params = request.GET
    else:
        cookie_term, _, cookie_year = request.COOKIES.get(DEFAULT_TERM_COOKIE, '').partition('-')
        term_params = {'term': cookie_term, 'year': cookie_year}
    selected_term = _requested_term(term_params, today)
    term_options = _newest_terms_first(
        set(_saved_terms(active_schedule)) | {current_term, selected_term}
    )

    if load_default and active_schedule:
        load_term = selected_term
        load_label = term_label(*load_term)
        dow_to_date = {_DOW_CODE.get(d.weekday()): d for d in week_dates}
        weekly_blocks = WeeklySchedule.objects.filter(
            schedule=active_schedule, user__in=visible_employees,
            term=load_term[0], year=load_term[1],
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
            messages.info(request, f"No {load_label} default weekly schedule is set for {active_schedule}.")
        else:
            messages.info(request, f"{load_label} default weekly schedule loaded — review and click Save to apply.")
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
            # Label every hour, the first row, and any short quarter-hour row
            'show_label': slot.minute == 0 or idx == 0 or slot.minute % 30 != 0,
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
        'grid_slots_json': _grid_slots_json(week_grid),
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
        'custom_color_pks_json': json.dumps([str(pk) for pk in custom_color_pks]),
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
        'employee_role_hours_json': role_hours.as_json(
            visible_employees, week_dates, key_str=lambda d: d.isoformat()
        ),
        'is_admin': is_admin, 'today': today,
        'load_default': load_default,
        'term_options': [
            {'term': t, 'year': y, 'label': term_label(t, y), 'selected': (t, y) == selected_term}
            for t, y in term_options
        ],
        'selected_term': selected_term[0], 'selected_year': selected_term[1],
        'default_term_cookie': DEFAULT_TERM_COOKIE,
    })


DEFAULT_BUILDER_DAYS = [d for d in DayOfWeek.choices]  # [('MON', 'Monday'), ...]


def _default_week_role_hours():
    """_RoleHours keyed by day code, from each role's weekly hours (no date
    overrides — the default week is dateless)."""
    weekly_by_role = {}

    def resolve(role, day_code):
        if role not in weekly_by_role:
            weekly_by_role[role] = hours.weekly_hours(role)
        start, end = weekly_by_role[role][day_code]
        return start, end, False

    return _RoleHours(resolve)


@login_required
@user_passes_test(_is_scheduler_or_admin)
def default_schedule_builder(request):
    """Schedulers define a recurring default week (day-of-week based) per
    Schedule per semester. Saved as WeeklySchedule rows; the live
    schedule_builder can load these to prefill a real week."""
    from account.models import Employee

    today = date.today()
    term, year = _requested_term(request.POST if request.method == 'POST' else request.GET, today)
    term_qs = f"&term={term}&year={year}"

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

    employee_colors, custom_color_pks = _employee_colors(active_schedule, visible_employees)

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

    # Employees who haven't marked the minimum required availability — flagged red in the sidebar
    low_availability_flags = {
        e.pk: (avail_minutes_by_user.get(e.pk, 0) / 60) < MIN_AVAILABILITY_HOURS
        for e in visible_employees
    }

    # Conflicts = this employee's default hours on OTHER schedules in the same
    # semester (keyed by day code, reusing the 'date' key so the existing
    # conflict-matching JS works unmodified).
    conflict_data = {}
    other_default_qs = WeeklySchedule.objects.none()
    if visible_employees:
        other_default_qs = WeeklySchedule.objects.filter(
            user__in=visible_employees, term=term, year=year,
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

    # Grid spans every member role's weekly hours; each employee is limited
    # to their own role's hours (role_hours.covers).
    role_hours = _default_week_role_hours()
    week_grid = role_hours.grid(
        _roles_of(visible_employees), [code for code, _label in DEFAULT_BUILDER_DAYS]
    )
    day_hours = {code: span[:2] for code, span in week_grid.day_hours.items()}
    slots = week_grid.slots
    slot_minutes = hours.slot_minutes(slots, week_grid.end)

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
                key = f"slot_{day_code}_{_slot_key(slot)}"
                for epk in request.POST.getlist(key):
                    if epk in emp_lookup and role_hours.covers(emp_lookup[epk].role, day_code, slot):
                        new_slots.setdefault(epk, set()).add((day_code, slot))

        violations = []
        for epk, slot_set in new_slots.items():
            emp = emp_lookup[epk]
            if not emp.part_time:
                continue
            new_mins = sum(slot_minutes[slot] for _, slot in slot_set)
            other_mins = sum(
                (blk.end_time.hour * 60 + blk.end_time.minute)
                - (blk.start_time.hour * 60 + blk.start_time.minute)
                for blk in WeeklySchedule.objects.filter(
                    user=emp, term=term, year=year,
                ).exclude(schedule=post_schedule)
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
            return redirect(f"{request.path}?schedule={post_schedule_pk}{term_qs}")

        WeeklySchedule.objects.filter(schedule=post_schedule, term=term, year=year).delete()

        outside_role_hours = set()  # names of employees with slots dropped below
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
                    if epk not in emp_lookup:
                        continue
                    if not role_hours.covers(emp_lookup[epk].role, day_code, slot):
                        outside_role_hours.add(emp_lookup[epk].get_full_name())
                        continue
                    per_emp.setdefault(epk, {})[slot] = epk
                    label = request.POST.get(f"{key}__label__{epk}", '')
                    per_emp_labels.setdefault(epk, {})[slot] = label
            for epk, emp_slots in per_emp.items():
                _slots_to_weekly_blocks(emp_slots, week_grid.slot_ends, post_schedule, term, year, day_code,
                                         emp_lookup, slot_labels=per_emp_labels.get(epk, {}))

        if outside_role_hours:
            messages.warning(
                request,
                "Some time was not saved because it falls outside the employee's role hours: "
                + ", ".join(sorted(outside_role_hours)),
            )
        messages.success(request, f"{term_label(term, year)} default weekly schedule saved for {post_schedule}.")
        return redirect(f"{request.path}?schedule={post_schedule_pk}{term_qs}")

    # ── GET: load existing WeeklySchedule blocks into cell state ─────────────
    blocks = list(
        WeeklySchedule.objects.filter(
            schedule=active_schedule, term=term, year=year,
        ).select_related('user')
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
            # Label every hour, the first row, and any short quarter-hour row
            'show_label': slot.minute == 0 or idx == 0 or slot.minute % 30 != 0,
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
        'grid_slots_json': _grid_slots_json(week_grid),
        'col_template': col_template,
        'day_header_cols': day_header_cols,
        'grid': grid,
        'allowed_schedules': allowed_schedules,
        'visible_employees': visible_employees,
        'employee_colors': employee_colors,
        'employee_colors_json': json.dumps(employee_colors),
        'custom_color_pks_json': json.dumps([str(pk) for pk in custom_color_pks]),
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
        'employee_role_hours_json': role_hours.as_json(
            visible_employees, [code for code, _label in DEFAULT_BUILDER_DAYS]
        ),
        'is_admin': is_admin,
        'term': term, 'year': year,
        'term_label': term_label(term, year),
        'term_choices': Term.choices,
        'saved_terms': [
            {'term': t, 'year': y, 'label': term_label(t, y)}
            for t, y in _saved_terms(active_schedule)
        ],
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
def employee_color(request, schedule_pk):
    """POST {emp_pk, color}: remember a scheduler-chosen color for one employee
    on this schedule. An empty color goes back to the default palette color.
    Returns the employee's resulting color."""
    schedule = get_object_or_404(Schedule, pk=schedule_pk)
    if not (request.user.is_admin or request.user.scheduler_of.filter(pk=schedule.pk).exists()):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    employee = schedule.members.filter(pk=data.get('emp_pk')).first()
    if not employee:
        return JsonResponse({'error': 'Not a member of this schedule'}, status=400)

    color = (data.get('color') or '').strip()
    if color:
        try:
            hex_color_validator(color)
        except ValidationError:
            return JsonResponse({'error': 'Invalid color'}, status=400)
        EmployeeColor.objects.update_or_create(
            schedule=schedule, user=employee, defaults={'color': color.upper()},
        )
    else:
        EmployeeColor.objects.filter(schedule=schedule, user=employee).delete()

    members = list(schedule.members.distinct().order_by('last_name', 'first_name'))
    colors, custom = _employee_colors(schedule, members)
    return JsonResponse({'color': colors[employee.pk], 'custom': employee.pk in custom})


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

    emp_lookup = {str(e.pk): e for e in Employee.objects.filter(member_of=schedule)}
    role_hours = _live_role_hours()
    # Rebuild the same rows the builder rendered for this whole week, so the
    # posted slot keys (including short quarter-hour rows) line up.
    week_start = _week_start(target_date)
    grid = role_hours.grid(
        _roles_of(emp_lookup.values()), [week_start + timedelta(days=i) for i in range(5)]
    )
    if target_date not in grid.day_hours:  # a weekend date isn't on the builder
        return JsonResponse({'error': 'Invalid date'}, status=400)
    if grid.day_hours[target_date][2]:
        ScheduleEntry.objects.filter(date=target_date, schedule=schedule).delete()
        return JsonResponse({'ok': True})

    ScheduleEntry.objects.filter(date=target_date, schedule=schedule).delete()

    per_emp = {}
    per_emp_labels = {}
    for slot in grid.slots:
        sk = f"{slot.hour:02d}_{slot.minute:02d}"
        key = f"slot_{date_iso}_{sk}"
        for epk in request.POST.getlist(key):
            if epk in emp_lookup and role_hours.covers(emp_lookup[epk].role, target_date, slot):
                per_emp.setdefault(epk, {})[slot] = epk
                label = request.POST.get(f"{key}__label__{epk}", '')
                per_emp_labels.setdefault(epk, {})[slot] = label

    for epk, emp_slots in per_emp.items():
        _slots_to_entries(emp_slots, grid.slot_ends, schedule, target_date, emp_lookup, request.user,
                          slot_labels=per_emp_labels.get(epk, {}))

    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_is_scheduler_or_admin)
@require_http_methods(['POST'])
def save_week_as_default(request):
    """Persist the schedule builder's currently-displayed week as the schedule's
    new default weekly template for the posted semester (the builder's
    dropdown; the current semester if missing), replacing whatever default
    that semester previously had."""
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
    role_hours = _live_role_hours()
    grid = role_hours.grid(_roles_of(emp_lookup.values()), week_dates)
    term, year = _requested_term(request.POST, date.today())

    WeeklySchedule.objects.filter(schedule=schedule, term=term, year=year).delete()

    for d in week_dates:
        day_code = _DOW_CODE.get(d.weekday())
        if not day_code or grid.day_hours[d][2]:
            continue
        per_emp = {}
        per_emp_labels = {}
        for slot in grid.slots:
            sk = f"{slot.hour:02d}_{slot.minute:02d}"
            key = f"slot_{d.isoformat()}_{sk}"
            for epk in request.POST.getlist(key):
                if epk in emp_lookup and role_hours.covers(emp_lookup[epk].role, d, slot):
                    per_emp.setdefault(epk, {})[slot] = epk
                    label = request.POST.get(f"{key}__label__{epk}", '')
                    per_emp_labels.setdefault(epk, {})[slot] = label
        for epk, emp_slots in per_emp.items():
            _slots_to_weekly_blocks(emp_slots, grid.slot_ends, schedule, term, year, day_code,
                                     emp_lookup, slot_labels=per_emp_labels.get(epk, {}))

    messages.success(request, f"This week's schedule is now the {term_label(term, year)} default for {schedule}.")
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

        xlsx_bytes = build_teams_shifts_xlsx(schedule_pks, date_from, date_to)
        filename = f"TeamsShifts_{date_from}_{date_to}.xlsx"
        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    return render(request, 'scheduling/export_teams_shifts.html', {'schedules': schedules})


def _slots_to_blocks(emp_slots, slot_ends, slot_labels=None):
    """Convert a {slot: emp_pk_str} mapping into per-employee contiguous
    (start_time, end_time, label) blocks, splitting on gaps or label changes.
    `slot_ends` is the grid's {row start: row end} (rows vary in length)."""
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
                expected = slot_ends[prev_slot]
                current_label = (slot_labels or {}).get(slot, '')
                if slot != expected or current_label != block_label:
                    blocks.append((block_start, expected, block_label))
                    block_start = slot
                    block_label = current_label
            prev_slot = slot

        if block_start is not None and prev_slot is not None:
            end_t = slot_ends[prev_slot]
            if block_start < end_t:
                blocks.append((block_start, end_t, block_label))
        result[epk] = blocks
    return result


def _slots_to_entries(emp_slots, slot_ends, schedule, d, emp_lookup, created_by, slot_labels=None):
    """Convert a {slot: emp_pk_str} mapping into contiguous ScheduleEntry objects."""
    for epk, blocks in _slots_to_blocks(emp_slots, slot_ends, slot_labels).items():
        emp = emp_lookup[epk]
        for start_t, end_t, label in blocks:
            ScheduleEntry.objects.create(
                user=emp, schedule=schedule,
                date=d, start_time=start_t, end_time=end_t,
                created_by=created_by,
                custom_label=label,
            )


def _slots_to_weekly_blocks(emp_slots, slot_ends, schedule, term, year, day_code, emp_lookup, slot_labels=None):
    """Convert a {slot: emp_pk_str} mapping into contiguous WeeklySchedule objects
    for one day-of-week of one semester's default week."""
    for epk, blocks in _slots_to_blocks(emp_slots, slot_ends, slot_labels).items():
        emp = emp_lookup[epk]
        for start_t, end_t, label in blocks:
            WeeklySchedule.objects.create(
                user=emp, schedule=schedule, term=term, year=year, day_of_week=day_code,
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