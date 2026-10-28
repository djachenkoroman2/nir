import datetime

from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import formset_data
from apps.ip.models import IntellectualProperty
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.tests import make_editor, make_teacher

from .models import DissertationDefense, ScientificSchool
from .period import report_period


class ReportPeriodTests(TestCase):
    def test_current_year_and_four_previous(self):
        self.assertEqual(report_period(datetime.date(2026, 10, 27)), (2022, 2026))
        self.assertEqual(report_period(datetime.date(2030, 1, 1)), (2026, 2030))


class IndicatorTests(TestCase):
    """Показатели считаются за период; первый год периода входит, год перед ним — нет."""

    def setUp(self):
        self.first_year, self.last_year = report_period()
        self.before = self.first_year - 1
        self.leader = make_teacher()
        self.school = ScientificSchool.objects.create(name='Анализ данных')
        self.school.leaders.add(self.leader)
        self.other = ScientificSchool.objects.create(name='Робототехника')
        self.other.leaders.add(self.leader)
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))

    def publication(self, year, schools=None, **fields):
        publication = Publication.objects.create(title=f'Публикация {year}', year=year, **fields)
        publication.schools.set(schools if schools is not None else [self.school])
        return publication

    def defense(self, year, kind=DissertationDefense.Kind.CANDIDATE, school=None):
        return DissertationDefense.objects.create(
            full_name='Аспирант', kind=kind, title='Тема', defense_date=datetime.date(year, 6, 1),
            school=school or self.school,
        )

    def ip(self, year, number, schools=None):
        item = IntellectualProperty.objects.create(
            kind='software', title='Программа', number=number, registration_date=datetime.date(year, 3, 1)
        )
        item.schools.set(schools if schools is not None else [self.school])
        return item

    def row(self, school=None):
        response = self.client.get(reverse('schools:school_list'))
        rows = {s.pk: s for s in response.context['school_list']}
        return rows[(school or self.school).pk], response.context['totals']

    def test_defenses(self):
        self.defense(self.first_year)
        self.defense(self.last_year, kind=DissertationDefense.Kind.DOCTOR)
        self.defense(self.before)
        row, _ = self.row()
        self.assertEqual((row.candidate_defenses, row.doctor_defenses, row.defenses_total), (1, 1, 2))

    def test_monographs_and_chapters_are_counted_separately(self):
        self.publication(self.first_year, kind=Publication.Kind.MONOGRAPH)
        self.publication(self.before, kind=Publication.Kind.MONOGRAPH)
        self.publication(self.last_year, kind=Publication.Kind.MONOGRAPH_CHAPTER)
        self.publication(self.last_year, kind=Publication.Kind.ARTICLE)
        row, _ = self.row()
        self.assertEqual((row.monographs, row.monograph_chapters), (1, 1))

    def test_vak_publications(self):
        self.publication(self.last_year, vak=Publication.VakCategory.K1)
        self.publication(self.first_year, vak=Publication.VakCategory.K3)
        self.publication(self.last_year, scopus=True)  # без категории ВАК — не считается
        self.publication(self.before, vak=Publication.VakCategory.K2)
        row, _ = self.row()
        self.assertEqual(row.vak_publications, 2)

    def test_intellectual_properties(self):
        self.ip(self.first_year, '1')
        self.ip(self.before, '2')
        row, _ = self.row()
        self.assertEqual(row.ip_total, 1)

    def test_records_without_school_link_are_not_counted(self):
        publication = self.publication(self.last_year, schools=[], vak=Publication.VakCategory.K1)
        PublicationAuthor.objects.create(publication=publication, teacher=self.leader)  # автор — ведущий учёный
        row, _ = self.row()
        self.assertEqual(row.vak_publications, 0)

    def test_totals_count_shared_records_once(self):
        self.publication(self.last_year, schools=[self.school, self.other], vak=Publication.VakCategory.K1)
        self.publication(self.last_year, schools=[self.other], vak=Publication.VakCategory.K2)
        self.defense(self.last_year)
        self.defense(self.last_year, school=self.other)
        row, totals = self.row()
        other_row, _ = self.row(self.other)
        self.assertEqual((row.vak_publications, other_row.vak_publications), (1, 2))
        self.assertEqual(totals['vak_publications'], 2)
        self.assertEqual(totals['defenses_total'], 2)

    def test_inactive_schools_hidden_by_default(self):
        self.other.is_active = False
        self.other.save()
        response = self.client.get(reverse('schools:school_list'))
        self.assertNotIn(self.other, response.context['school_list'])
        response = self.client.get(reverse('schools:school_list'), {'all': '1'})
        self.assertIn(self.other, response.context['school_list'])

    def test_detail_lists_match_indicators(self):
        monograph = self.publication(self.last_year, kind=Publication.Kind.MONOGRAPH)
        old = self.publication(self.before, kind=Publication.Kind.MONOGRAPH)
        old.title = 'Старая монография'
        old.save()
        self.defense(self.before)
        response = self.client.get(self.school.get_absolute_url())
        self.assertEqual(list(response.context['monographs']), [monograph])
        self.assertNotContains(response, 'Старая монография')
        self.assertEqual(len(response.context['earlier_defenses']), 1)

    def test_summary_query_count_does_not_grow_with_schools(self):
        def query_count():
            with CaptureQueriesContext(connection) as context:
                self.client.get(reverse('schools:school_list'))
            return len(context)

        baseline = query_count()
        for index in range(5):
            school = ScientificSchool.objects.create(name=f'Школа {index}')
            school.leaders.add(make_teacher(last_name=f'Учёный{index}'))
            self.publication(self.last_year, schools=[school], vak=Publication.VakCategory.K1)
            self.defense(self.last_year, school=school)
        self.assertEqual(query_count(), baseline)


class SchoolAccessTests(TestCase):
    def setUp(self):
        self.school = ScientificSchool.objects.create(name='Анализ данных')
        self.school.leaders.add(make_teacher())

    def edit_urls(self):
        return [reverse('schools:school_create'), reverse('schools:school_update', args=[self.school.pk]),
                reverse('schools:school_delete', args=[self.school.pk]),
                reverse('schools:defense_create', args=[self.school.pk])]

    def test_anonymous_is_redirected(self):
        url = reverse('schools:school_list')
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_reader_and_teacher_can_only_view(self):
        reader = User.objects.create_user(username='reader', password='secret')
        teacher_user = User.objects.create_user(username='teacher', password='secret')
        teacher_user.groups.add(Group.objects.get(name='Преподаватели'))
        make_teacher(last_name='Смирнов', user=teacher_user)
        self.client.force_login(reader)
        response = self.client.get(reverse('schools:school_list'))
        self.assertContains(response, 'Анализ данных')
        self.assertNotContains(response, reverse('schools:school_create'))
        for url in self.edit_urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)
        # Преподаватель в личном кабинете сводную таблицу не видит; изменить школы и защиты не может.
        self.client.force_login(teacher_user)
        self.assertEqual(self.client.get(reverse('schools:school_list')).status_code, 403)
        for url in self.edit_urls():
            self.assertIn(self.client.get(url).status_code, (403, 404), url)

    def test_editor_creates_school_and_defense(self):
        self.client.force_login(make_editor())
        leader = make_teacher(last_name='Петров')
        response = self.client.post(reverse('schools:school_create'), {
            'name': 'Компьютерное зрение', 'leaders': [leader.pk], 'is_active': 'on',
        })
        school = ScientificSchool.objects.get(name='Компьютерное зрение')
        self.assertRedirects(response, school.get_absolute_url())

        response = self.client.post(reverse('schools:defense_create', args=[school.pk]), {
            'full_name': 'Сидоров С. С.', 'kind': 'candidate', 'title': 'Тема',
            'defense_date': f'{report_period()[1]}-02-01', 'school': school.pk, 'supervisor': leader.pk,
        })
        self.assertRedirects(response, school.get_absolute_url())
        self.assertEqual(school.defenses.get().supervisor, leader)

    def test_school_requires_leader(self):
        self.client.force_login(make_editor())
        response = self.client.post(reverse('schools:school_create'), {'name': 'Без учёных', 'is_active': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ScientificSchool.objects.filter(name='Без учёных').exists())

    def test_school_with_defenses_is_not_deleted(self):
        DissertationDefense.objects.create(full_name='А', kind='candidate', title='Т',
                                           defense_date='2025-01-01', school=self.school)
        self.client.force_login(make_editor())
        response = self.client.get(reverse('schools:school_delete', args=[self.school.pk]))
        self.assertTrue(response.context['delete_blocked'])
        response = self.client.post(reverse('schools:school_delete', args=[self.school.pk]))
        self.assertRedirects(response, self.school.get_absolute_url())
        self.assertTrue(ScientificSchool.objects.filter(pk=self.school.pk).exists())

    def test_deleting_school_keeps_publications(self):
        publication = Publication.objects.create(title='Статья', year=2026)
        publication.schools.add(self.school)
        self.client.force_login(make_editor())
        self.client.post(reverse('schools:school_delete', args=[self.school.pk]))
        self.assertFalse(ScientificSchool.objects.filter(pk=self.school.pk).exists())
        self.assertTrue(Publication.objects.filter(pk=publication.pk).exists())

    def test_teacher_links_own_publication_to_school(self):
        teacher_user = User.objects.create_user(username='teacher', password='secret')
        teacher_user.groups.add(Group.objects.get(name='Преподаватели'))
        me = make_teacher(last_name='Смирнов', user=teacher_user)
        self.client.force_login(teacher_user)
        data = {'kind': 'article', 'title': 'Моя статья', 'year': '2026', 'schools': [self.school.pk]}
        data.update(formset_data('authors', [{'teacher': me.pk, 'external_name': ''}]))
        self.client.post(reverse('publications:publication_create'), data)
        self.assertEqual(list(Publication.objects.get(title='Моя статья').schools.all()), [self.school])
