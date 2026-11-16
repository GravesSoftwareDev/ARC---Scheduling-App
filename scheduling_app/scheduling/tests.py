import datetime

from django.test import TestCase
from django.urls import reverse

from account.models import Employee
from .models import AvailabilityWindow, Term, WeeklyAvailability, term_for_date, term_label, min_availability_hours
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
