from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import formset_data
from apps.staff.tests import make_editor, make_teacher

from .models import Publication, PublicationAuthor


def publication_data(authors, **fields):
    data = {'kind': Publication.Kind.ARTICLE, 'title': 'Статья', 'year': '2026', 'source': 'Журнал'}
    data.update(fields)
    data.update(formset_data('authors', authors))
    return data


class PublicationModelTests(TestCase):
    def test_imprint(self):
        publication = Publication(title='Статья', year=2026, source='Вестник', volume='5', issue='2', pages='10–20')
        self.assertEqual(publication.imprint, 'Вестник. — 2026. — Т. 5. — № 2. — С. 10–20')

    def test_indexing_labels(self):
        publication = Publication(vak='K1', rinc=True, rinc_core=True, scopus=True, quartile='Q2')
        self.assertEqual(publication.indexing, ['ВАК К1', 'ядро РИНЦ', 'Scopus', 'Q2'])


class PublicationEditTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Смирнов')
        self.client.force_login(make_editor())

    def test_create_with_teacher_and_external_author_keeps_order(self):
        response = self.client.post(reverse('publications:publication_create'), publication_data([
            {'teacher': '', 'external_name': 'Петров П. П.'},
            {'teacher': self.teacher.pk, 'external_name': ''},
        ], rinc_core='on'))
        publication = Publication.objects.get()
        self.assertRedirects(response, publication.get_absolute_url())
        self.assertEqual(publication.authors_display, 'Петров П. П., Смирнов И. И.')
        self.assertTrue(publication.rinc, 'ядро РИНЦ подразумевает РИНЦ')

    def test_authors_are_required(self):
        response = self.client.post(reverse('publications:publication_create'), publication_data([
            {'teacher': '', 'external_name': ''},
        ]))
        self.assertContains(response, 'Укажите хотя бы одного автора.')
        self.assertFalse(Publication.objects.exists())

    def test_duplicate_teacher_is_rejected(self):
        response = self.client.post(reverse('publications:publication_create'), publication_data([
            {'teacher': self.teacher.pk, 'external_name': ''},
            {'teacher': self.teacher.pk, 'external_name': ''},
        ]))
        self.assertContains(response, 'Один и тот же преподаватель указан несколько раз.')
        self.assertFalse(Publication.objects.exists())

    def test_author_needs_exactly_one_of_teacher_or_name(self):
        response = self.client.post(reverse('publications:publication_create'), publication_data([
            {'teacher': self.teacher.pk, 'external_name': 'Петров П. П.'},
        ]))
        self.assertContains(response, 'что-то одно')
        self.assertFalse(Publication.objects.exists())

    def test_teacher_with_publication_is_not_deleted(self):
        publication = Publication.objects.create(title='Статья', year=2026)
        PublicationAuthor.objects.create(publication=publication, teacher=self.teacher)
        response = self.client.get(reverse('staff:teacher_delete', args=[self.teacher.pk]))
        self.assertTrue(response.context['delete_blocked'])
        self.client.post(reverse('staff:teacher_delete', args=[self.teacher.pk]))
        self.assertTrue(type(self.teacher).objects.filter(pk=self.teacher.pk).exists())


class PublicationListTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        scopus = Publication.objects.create(title='Статья в Scopus', year=2025, scopus=True)
        PublicationAuthor.objects.create(publication=scopus, teacher=self.teacher)
        Publication.objects.create(title='Пособие', year=2026, kind=Publication.Kind.STUDY_GUIDE, vak='K2')
        self.reader = User.objects.create_user(username='reader', password='secret')
        self.client.force_login(self.reader)

    def titles(self, **params):
        response = self.client.get(reverse('publications:publication_list'), params)
        return [p.title for p in response.context['publication_list']]

    def test_filters(self):
        self.assertEqual(self.titles(year='2025'), ['Статья в Scopus'])
        self.assertEqual(self.titles(index='scopus'), ['Статья в Scopus'])
        self.assertEqual(self.titles(index='vak'), ['Пособие'])
        self.assertEqual(self.titles(kind='study_guide'), ['Пособие'])
        self.assertEqual(self.titles(q='scopus'), ['Статья в Scopus'])

    def test_reader_cannot_edit(self):
        response = self.client.get(reverse('publications:publication_list'))
        self.assertNotContains(response, reverse('publications:publication_create'))
        self.assertEqual(self.client.get(reverse('publications:publication_create')).status_code, 403)

    def test_publication_is_shown_on_teacher_page(self):
        response = self.client.get(self.teacher.get_absolute_url())
        self.assertContains(response, 'Статья в Scopus')

    def test_anonymous_is_redirected(self):
        url = reverse('publications:publication_list')
        self.client.logout()
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")
