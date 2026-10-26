import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import formset_data
from apps.publications.models import Publication
from apps.staff.tests import make_editor, make_teacher

from .forms import ReportForm
from .models import Conference, Report


class ConferenceModelTests(TestCase):
    def test_end_date_before_start_date_is_invalid(self):
        conference = Conference(title='Конференция', level='national',
                                start_date=datetime.date(2026, 5, 2), end_date=datetime.date(2026, 5, 1))
        with self.assertRaises(ValidationError):
            conference.full_clean()


class ReportTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.conference = Conference.objects.create(title='Информатика-2026', level='international',
                                                    start_date='2026-09-10')
        self.theses = Publication.objects.create(title='Тезисы', year=2026, kind=Publication.Kind.THESES)

    def test_editor_adds_report_with_speakers_and_theses(self):
        self.client.force_login(make_editor())
        data = {'title': 'Доклад о методе', 'form': Report.Form.PLENARY, 'publication': self.theses.pk}
        data.update(formset_data('speakers', [
            {'teacher': self.teacher.pk, 'external_name': ''},
            {'teacher': '', 'external_name': 'Гость Г. Г.'},
        ]))
        response = self.client.post(reverse('conferences:report_create', args=[self.conference.pk]), data)
        self.assertRedirects(response, self.conference.get_absolute_url())
        report = Report.objects.get()
        self.assertEqual(report.conference, self.conference)
        self.assertEqual(report.speakers_display, 'Иванов И. И., Гость Г. Г.')

        page = self.client.get(self.conference.get_absolute_url())
        self.assertContains(page, 'Доклад о методе')
        self.assertContains(page, 'Тезисы')
        self.assertContains(self.client.get(self.teacher.get_absolute_url()), 'Доклад о методе')

    def test_speakers_are_required(self):
        self.client.force_login(make_editor())
        data = {'title': 'Доклад', 'form': Report.Form.SECTION}
        data.update(formset_data('speakers', [{'teacher': '', 'external_name': ''}]))
        response = self.client.post(reverse('conferences:report_create', args=[self.conference.pk]), data)
        self.assertContains(response, 'Укажите хотя бы одного докладчика.')

    def test_publication_already_linked_is_not_offered(self):
        Report.objects.create(conference=self.conference, title='Первый', publication=self.theses)
        self.assertNotIn(self.theses, ReportForm().fields['publication'].queryset)
        other = Report.objects.get(title='Первый')
        self.assertIn(self.theses, ReportForm(instance=other).fields['publication'].queryset)

    def test_reader_cannot_add_report(self):
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        page = self.client.get(self.conference.get_absolute_url())
        self.assertNotContains(page, reverse('conferences:report_create', args=[self.conference.pk]))
        response = self.client.get(reverse('conferences:report_create', args=[self.conference.pk]))
        self.assertEqual(response.status_code, 403)


class ConferenceListTests(TestCase):
    def test_filter_by_level_and_year(self):
        Conference.objects.create(title='Международная', level='international', start_date='2025-05-01')
        Conference.objects.create(title='Вузовская', level='university', start_date='2026-04-01')
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        url = reverse('conferences:conference_list')
        titles = lambda **params: [c.title for c in self.client.get(url, params).context['conference_list']]
        self.assertEqual(titles(level='university'), ['Вузовская'])
        self.assertEqual(titles(year='2025'), ['Международная'])
