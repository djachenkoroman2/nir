import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import formset_data
from apps.research.models import ResearchProject
from apps.staff.tests import make_editor, make_teacher

from .models import IntellectualProperty


class IntellectualPropertyModelTests(TestCase):
    def test_registration_before_application_is_invalid(self):
        item = IntellectualProperty(kind='software', title='Программа', number='2026610001',
                                    application_date=datetime.date(2026, 3, 1),
                                    registration_date=datetime.date(2026, 2, 1))
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn('registration_date', context.exception.message_dict)

    def test_number_is_unique_within_kind(self):
        IntellectualProperty.objects.create(kind='software', title='А', number='1', registration_date='2026-01-01')
        duplicate = IntellectualProperty(kind='software', title='Б', number='1', registration_date='2026-01-01')
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        IntellectualProperty(kind='database', title='В', number='1', registration_date='2026-01-01').full_clean()


class IntellectualPropertyViewTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.project = ResearchProject.objects.create(title='НИОКР', start_date='2026-01-01')

    def test_editor_creates_ip_linked_to_project(self):
        self.client.force_login(make_editor())
        data = {'kind': 'invention', 'title': 'Способ', 'number': '2800000',
                'registration_date': '2026-04-01', 'project': self.project.pk}
        data.update(formset_data('authors', [{'teacher': self.teacher.pk, 'external_name': ''}]))
        response = self.client.post(reverse('ip:ip_create'), data)
        item = IntellectualProperty.objects.get()
        self.assertRedirects(response, item.get_absolute_url())
        self.assertEqual(item.authors_display, 'Иванов И. И.')
        self.assertContains(self.client.get(self.project.get_absolute_url()), 'Способ')

    def test_reader_can_view_but_not_edit(self):
        item = IntellectualProperty.objects.create(kind='software', title='Программа', number='1',
                                                   registration_date='2025-06-01')
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        response = self.client.get(reverse('ip:ip_list'), {'year': '2025'})
        self.assertContains(response, 'Программа')
        self.assertNotContains(response, reverse('ip:ip_create'))
        self.assertEqual(self.client.get(reverse('ip:ip_update', args=[item.pk])).status_code, 403)
