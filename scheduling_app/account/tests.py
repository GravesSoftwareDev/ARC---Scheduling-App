from django.test import TestCase

# Create your tests here.


class AvailabilityExceptionFormTests(TestCase):
    def _data(self, **extra):
        data = {'username': 'emp', 'email': 'e@example.com', 'first_name': 'E', 'last_name': 'M',
                'role': 'TUTOR'}
        data.update(extra)
        return data

    def test_exception_date_requires_term_and_year(self):
        from .forms import EditEmployeeForm
        form = EditEmployeeForm(self._data(availability_override_until='2026-12-01'))
        self.assertFalse(form.is_valid())
        self.assertIn('availability_override_term', form.errors)
        self.assertIn('availability_override_year', form.errors)

    def test_exception_saves_term(self):
        from .forms import EditEmployeeForm
        form = EditEmployeeForm(self._data(
            availability_override_until='2026-12-01',
            availability_override_term='FF', availability_override_year=2026,
        ))
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()
        self.assertEqual((emp.availability_override_term, emp.availability_override_year), ('FF', 2026))

    def test_clearing_date_clears_term(self):
        from .forms import EditEmployeeForm
        form = EditEmployeeForm(self._data(availability_override_term='FF', availability_override_year=2026))
        self.assertTrue(form.is_valid(), form.errors)
        emp = form.save()
        self.assertEqual((emp.availability_override_term, emp.availability_override_year), ('', None))
