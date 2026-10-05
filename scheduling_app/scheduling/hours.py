"""Operating-hours resolution and grid rows, shared by the scheduling and
dashboard views.

Weekly hours can be set per role. For a given role and date, the first match wins:
  1. a DateOperatingHours row for that date (applies to every role)
  2. that role's weekly OperatingHours row for the weekday
  3. the default (blank-role) weekly OperatingHours row for the weekday
  4. DEFAULT_OPEN–DEFAULT_CLOSE

Open/close times are on the quarter hour. Grids use GRID_MINUTES-wide rows on
:00/:30, plus a short row wherever an open/close time falls between them
(e.g. a 7:45 open adds a 7:45–8:00 row) — see build_slots().
"""

from datetime import time

from .models import DateOperatingHours, DayOfWeek, OperatingHours

DEFAULT_OPEN = time(8, 0)
DEFAULT_CLOSE = time(17, 0)
GRID_MINUTES = 30

DOW_CODE = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}


def weekly_hours(role=''):
    """{day_code: (open, close)} for every weekday, for the given role."""
    role = role or ''
    rows = {
        (oh.role, oh.day_of_week): oh
        for oh in OperatingHours.objects.filter(role__in={'', role})
    }
    result = {}
    for day_code, _label in DayOfWeek.choices:
        oh = rows.get((role, day_code)) or rows.get(('', day_code))
        result[day_code] = (oh.start_time, oh.end_time) if oh else (DEFAULT_OPEN, DEFAULT_CLOSE)
    return result


def hours_for_date(d, role=''):
    """(open, close, is_closed) for a specific date and role."""
    doh = DateOperatingHours.objects.filter(date=d).first()
    if doh:
        if doh.is_closed:
            return None, None, True
        return doh.start_time, doh.end_time, False

    day_code = DOW_CODE[d.weekday()]
    if day_code in dict(DayOfWeek.choices):
        start, end = weekly_hours(role)[day_code]
        return start, end, False
    return DEFAULT_OPEN, DEFAULT_CLOSE, False


def combine_spans(spans):
    """Merge several (open, close, is_closed) spans into the one window that
    covers all of them — closed only if every span is closed."""
    open_spans = [(s, e) for s, e, closed in spans if not closed and s]
    if not open_spans:
        return None, None, True
    return min(s for s, _ in open_spans), max(e for _, e in open_spans), False


def span_edges(spans):
    """Every open/close time in an iterable of (open, close, is_closed) spans."""
    return {t for s, e, closed in spans if not closed and s for t in (s, e)}


def _to_min(t):
    return t.hour * 60 + t.minute


def _to_time(m):
    return time(m // 60, m % 60)


def build_slots(start, end, edges=()):
    """Row start times from `start` up to (not including) `end`: every
    :00/:30, plus `start` and any of `edges` in between, so a row is
    GRID_MINUTES long except next to a quarter-hour open/close time.

    Every grid and every save path that reads a grid's POST data must build
    its rows from the same start/end/edges, or slot keys won't line up."""
    s, e = _to_min(start), _to_min(end)
    first_aligned = -(-s // GRID_MINUTES) * GRID_MINUTES  # round up to :00/:30
    points = set(range(first_aligned, e, GRID_MINUTES))
    points.add(s)
    points.update(m for m in map(_to_min, edges) if s < m < e)
    return [_to_time(m) for m in sorted(points)]


def slot_ends(slots, end):
    """{row start: row end} — each row ends where the next begins."""
    return dict(zip(slots, list(slots[1:]) + [end]))


def slot_minutes(slots, end):
    """{row start: length in minutes}."""
    return {s: _to_min(e) - _to_min(s) for s, e in slot_ends(slots, end).items()}
