import datetime

from django.test import TestCase
from django.urls import reverse

from account.models import Employee
from .models import AvailabilityWindow, Term, TermPreferences, WeeklyAvailability, term_for_date, term_label, min_availability_hours
from .views import _newest_terms_first


class FinalsTermTests(TestCase):
    def test_finals_terms_sort_right_after_their_semester(self):
        pairs = [('FA', 2026), ('FF', 2026), ('SP', 2027), ('SF', 2027), ('SU', 2027), ('UF', 2027)]
        self.assertEqual(
            _newest_terms_first(pairs),
            [('UF', 2027), ('SU', 2027), ('SF', 2027), ('SP', 2027), ('FF', 2026), ('FA', 2026)],
        )

    def test_labels(self):
        self.assertEqual(term_label(Term.FALL_FINALS, 2026), 'FF26')
        self.assertEqual(term_label(Term.SPRING_FINALS, 2027), 'SF27')
        self.assertEqual(term_label(Term.SUMMER_FINALS, 2027), 'UF27')

    def test_finals_have_no_minimum_hours(self):
        for t in (Term.SPRING_FINALS, Term.SUMMER_FINALS, Term.FALL_FINALS):
            self.assertEqual(min_availability_hours(t), 0)
        for t in (Term.SPRING, Term.SUMMER, Term.FALL):
            self.assertEqual(min_availability_hours(t), 10)

    def test_availability_page_warns_only_for_regular_terms(self):
        emp = Employee.objects.create_user('emp', password='pw')
        self.client.force_login(emp)
        url = reverse('scheduling:manage_availability')
        self.assertTrue(self.client.get(url + '?term=FA&year=2026').context['below_min_availability'])
        self.assertFalse(self.client.get(url + '?term=FF&year=2026').context['below_min_availability'])

    def test_dates_never_resolve_to_finals(self):
        self.assertEqual(term_for_date(datetime.date(2026, 12, 15)), Term.FALL)
        self.assertEqual(term_for_date(datetime.date(2027, 5, 10)), Term.SPRING)
        self.assertEqual(term_for_date(datetime.date(2027, 7, 28)), Term.SUMMER)


class PerTermAvailabilityWindowTests(TestCase):
    SLOT = 'slot_MON_10_00'  # inside the default operating hours

    def setUp(self):
        self.admin = Employee.objects.create_user('admin', password='pw', is_admin=True)
        self.employee = Employee.objects.create_user('emp', password='pw')
        self.url = reverse('scheduling:manage_availability')

    def _save_availability(self, term, year):
        self.client.force_login(self.employee)
        self.client.post(self.url, {'term': term, 'year': year, self.SLOT: 'AVAILABLE'})
        return WeeklyAvailability.objects.filter(user=self.employee, term=term, year=year).exists()

    def test_term_without_window_is_closed(self):
        self.assertFalse(AvailabilityWindow.for_term('FF', 2026).is_currently_open())
        self.assertFalse(self._save_availability('FF', 2026))
        self.assertFalse(AvailabilityWindow.objects.exists())  # viewing doesn't create rows

    def test_admin_opens_one_term_only(self):
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('scheduling:availability_window'),
            {'term': 'FF', 'year': 2026, 'is_open': 'on'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AvailabilityWindow.objects.get(term='FF', year=2026).is_open)

        self.assertTrue(self._save_availability('FF', 2026))
        self.assertFalse(self._save_availability('FA', 2026))

    def test_date_range_opens_term(self):
        today = datetime.date.today()
        AvailabilityWindow.objects.create(
            term='SF', year=2027, is_open=False,
            opens_at=today - datetime.timedelta(days=1),
            closes_at=today + datetime.timedelta(days=1),
        )
        self.assertTrue(self._save_availability('SF', 2027))

    def test_admin_page_renders_and_lists_windows(self):
        AvailabilityWindow.objects.create(term='FF', year=2026, is_open=True)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('scheduling:availability_window') + '?term=FF&year=2026')
        self.assertContains(resp, 'Editing enabled for FF26')
        self.assertContains(resp, 'Fall Finals 2026')

    def test_exception_applies_to_its_term_only(self):
        self.employee.availability_override_until = datetime.date.today()
        self.employee.availability_override_term = 'FF'
        self.employee.availability_override_year = 2026
        self.employee.save()
        self.assertTrue(self._save_availability('FF', 2026))
        self.assertFalse(self._save_availability('FA', 2026))
        self.assertFalse(self._save_availability('FF', 2027))

    def test_expired_exception_does_not_apply(self):
        self.employee.availability_override_until = datetime.date.today() - datetime.timedelta(days=1)
        self.employee.availability_override_term = 'FF'
        self.employee.availability_override_year = 2026
        self.employee.save()
        self.assertFalse(self._save_availability('FF', 2026))

    def test_non_admin_cannot_manage_windows(self):
        self.client.force_login(self.employee)
        self.client.post(
            reverse('scheduling:availability_window'),
            {'term': 'FF', 'year': 2026, 'is_open': 'on'},
        )
        self.assertFalse(AvailabilityWindow.objects.exists())


class PerTermPreferencesTests(TestCase):
    """Desired weekly hours + lunch break are saved per term, like availability."""

    def setUp(self):
        self.employee = Employee.objects.create_user('emp', password='pw')
        self.url = reverse('scheduling:manage_availability')
        for term in ('FA', 'SP'):
            AvailabilityWindow.objects.create(term=term, year=2027, is_open=True)
        self.client.force_login(self.employee)

    def _save(self, term, hours, lunch=False):
        data = {'term': term, 'year': 2027, 'desired_weekly_hours': hours}
        if lunch:
            data['wants_lunch_break'] = 'on'
        self.client.post(self.url, data)

    def test_each_term_keeps_its_own_preferences(self):
        self._save('FA', 19.5, lunch=True)
        self._save('SP', 10)
        fa = TermPreferences.objects.get(user=self.employee, term='FA', year=2027)
        sp = TermPreferences.objects.get(user=self.employee, term='SP', year=2027)
        self.assertEqual((fa.desired_weekly_hours, fa.wants_lunch_break), (19.5, True))
        self.assertEqual((sp.desired_weekly_hours, sp.wants_lunch_break), (10, False))

        form = self.client.get(self.url + '?term=FA&year=2027').context['preferences_form']
        self.assertEqual(form.instance.desired_weekly_hours, 19.5)

    def test_viewing_a_term_does_not_create_preferences(self):
        self.client.get(self.url + '?term=FA&year=2027')
        self.assertFalse(TermPreferences.objects.exists())

    def test_copy_from_prefills_preferences(self):
        self._save('FA', 15, lunch=True)
        WeeklyAvailability.objects.create(
            user=self.employee, term='FA', year=2027, day_of_week='MON',
            start_time=datetime.time(10), end_time=datetime.time(11),
        )
        form = self.client.get(self.url + '?term=SP&year=2027&copy_from=FA-2027').context['preferences_form']
        self.assertEqual(form.instance.desired_weekly_hours, 15)
        self.assertTrue(form.instance.wants_lunch_break)
        self.assertFalse(TermPreferences.objects.filter(term='SP').exists())  # unsaved until Save
