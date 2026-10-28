"""Личный кабинет преподавателя и адъюнкта: видно только своё (кабинет курсанта — apps/students/test_cabinet.py)."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.adjuncts.models import Task
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.models import ScientificSchool
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import named_urls_without_arguments
from apps.students.tests import make_student, make_teacher_user

from .cabinet import ADJUNCT, RULES, TEACHER

CLOSED_LISTS = [
    'staff:teacher_list', 'research:project_list', 'publications:publication_list', 'ip:ip_list',
    'conferences:conference_list', 'schools:school_list', 'students:student_list', 'adjuncts:adjunct_list',
    'admin:index',
]


def publication_by(title, **author):
    publication = Publication.objects.create(title=title, year=2026)
    PublicationAuthor.objects.create(publication=publication, order=1, **author)
    return publication


class CabinetFixture(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Руководителев')
        self.colleague = make_teacher(last_name='Коллегин')
        self.student = make_student(supervisor=self.teacher)
        self.foreign_student = make_student(last_name='Чужой', supervisor=self.colleague)
        self.school = ScientificSchool.objects.create(name='Моя школа')
        self.school.leaders.add(self.teacher)
        self.foreign_school = ScientificSchool.objects.create(name='Чужая школа')
        self.adjunct = make_adjunct(self.teacher, school=self.school)
        self.foreign_adjunct = make_adjunct(self.colleague, last_name='Соседов')
        self.project = ResearchProject.objects.create(title='Мой проект', start_date='2026-01-01')
        Participant.objects.create(project=self.project, teacher=self.teacher)
        self.foreign_project = ResearchProject.objects.create(title='Чужой проект', start_date='2026-01-01')
        Participant.objects.create(project=self.foreign_project, teacher=self.colleague)
        self.mine = publication_by('Моя статья', teacher=self.teacher)
        PublicationAuthor.objects.create(publication=self.mine, teacher=self.colleague, order=2)
        self.foreign = publication_by('Чужая статья', teacher=self.colleague)
        self.student_publication = publication_by('Статья подопечного', student=self.student)
        self.conference = Conference.objects.create(title='Конференция', level='national', start_date='2026-05-01')
        report = Report.objects.create(conference=self.conference, title='Мой доклад')
        ReportSpeaker.objects.create(report=report, teacher=self.teacher)
        self.foreign_conference = Conference.objects.create(title='Чужая', level='national', start_date='2026-06-01')
        self.task = Task.objects.create(student=self.student, title='Задача подопечного')
        self.foreign_task = Task.objects.create(student=self.foreign_student, title='Чужая задача')

    def status(self, url):
        return self.client.get(url).status_code


class TeacherCabinetTests(CabinetFixture):
    def setUp(self):
        super().setUp()
        self.user = make_teacher_user(self.teacher)
        self.client.force_login(self.user)

    def test_open_pages(self):
        for url in [
            self.teacher.get_absolute_url(), self.mine.get_absolute_url(),
            self.student_publication.get_absolute_url(), self.project.get_absolute_url(),
            self.school.get_absolute_url(), self.conference.get_absolute_url(),
            self.student.get_absolute_url(), self.student.get_tasks_url(), self.adjunct.get_absolute_url(),
            self.task.get_absolute_url(), reverse('tasks:my_tasks'), reverse('publications:publication_create'),
            reverse('ip:ip_create'), reverse('conferences:report_choose'),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.status(url), 200)

    def test_closed_lists_and_foreign_records(self):
        for name in CLOSED_LISTS:
            with self.subTest(name=name):
                self.assertEqual(self.status(reverse(name)), 403)
        for url in [
            self.colleague.get_absolute_url(), self.foreign.get_absolute_url(),
            self.foreign_project.get_absolute_url(), self.foreign_school.get_absolute_url(),
            self.foreign_conference.get_absolute_url(), self.foreign_student.get_absolute_url(),
            self.foreign_adjunct.get_absolute_url(), self.foreign_task.get_absolute_url(),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.status(url), 404)

    def test_pages_not_in_whitelist_are_closed_by_default(self):
        for name in sorted(set(named_urls_without_arguments()) - set(RULES[TEACHER])):
            with self.subTest(name=name):
                self.assertEqual(self.status(reverse(name)), 403)

    def test_home_is_own_card_with_cabinet_actions(self):
        self.assertRedirects(self.client.get('/'), self.teacher.get_absolute_url())
        response = self.client.get(self.teacher.get_absolute_url())
        self.assertTrue(response.context['is_cabinet'])
        for text in ('Добавить публикацию', 'Добавить РИД', 'Добавить доклад', 'id="supervision"'):
            self.assertContains(response, text)

    def test_header_has_only_own_items(self):
        response = self.client.get(self.teacher.get_absolute_url())
        for text in ('Мой кабинет', 'Мои подопечные', 'Мои задачи'):
            self.assertContains(response, text)
        for name in CLOSED_LISTS:
            with self.subTest(name=name):
                self.assertNotContains(response, f'href="{reverse(name)}"')

    def test_closed_cards_are_shown_as_text(self):
        response = self.client.get(self.mine.get_absolute_url())
        self.assertContains(response, 'Коллегин')
        self.assertNotContains(response, self.colleague.get_absolute_url())
        self.assertContains(response, self.teacher.get_absolute_url())

    def test_new_supervisor_gets_access(self):
        self.student.supervisor = self.colleague
        self.student.save()
        self.assertEqual(self.status(self.student.get_absolute_url()), 404)
        self.assertEqual(self.status(self.task.get_absolute_url()), 404)
        self.client.force_login(make_teacher_user(self.colleague, 'colleague'))
        self.assertEqual(self.status(self.student.get_absolute_url()), 200)
        self.assertEqual(self.status(self.task.get_absolute_url()), 200)

    def test_after_deleting_publication_goes_to_cabinet(self):
        response = self.client.post(reverse('publications:publication_delete', args=[self.mine.pk]))
        self.assertRedirects(response, reverse('core:home'), target_status_code=302)


class AdjunctCabinetTests(CabinetFixture):
    def setUp(self):
        super().setUp()
        self.user = make_adjunct_user(self.adjunct)
        self.client.force_login(self.user)
        self.own = publication_by('Статья адъюнкта', adjunct=self.adjunct)

    def test_open_pages(self):
        for url in [
            self.adjunct.get_absolute_url(), reverse('adjuncts:adjunct_contacts', args=[self.adjunct.pk]),
            self.adjunct.get_tasks_url(), self.own.get_absolute_url(), self.school.get_absolute_url(),
            reverse('tasks:my_tasks'), reverse('publications:publication_create'), reverse('ip:ip_create'),
            reverse('adjuncts:achievement_create', args=[self.adjunct.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.status(url), 200)

    def test_closed_lists_and_foreign_records(self):
        for name in CLOSED_LISTS:
            with self.subTest(name=name):
                self.assertEqual(self.status(reverse(name)), 403)
        for url in [
            self.mine.get_absolute_url(), self.foreign_school.get_absolute_url(),
            self.foreign_adjunct.get_absolute_url(), self.conference.get_absolute_url(), self.task.get_absolute_url(),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.status(url), 404)
        # Карточек преподавателей (в том числе руководителя), курсантов и НИОКР нет в белом списке адъюнкта.
        for url in [self.teacher.get_absolute_url(), self.student.get_absolute_url(), self.project.get_absolute_url()]:
            with self.subTest(url=url):
                self.assertEqual(self.status(url), 403)

    def test_pages_not_in_whitelist_are_closed_by_default(self):
        for name in sorted(set(named_urls_without_arguments()) - set(RULES[ADJUNCT])):
            with self.subTest(name=name):
                self.assertEqual(self.status(reverse(name)), 403)

    def test_cabinet_shows_supervisor_as_text_and_own_school_as_link(self):
        self.assertRedirects(self.client.get('/'), self.adjunct.get_absolute_url())
        response = self.client.get(self.adjunct.get_absolute_url())
        self.assertContains(response, self.teacher.full_name)
        self.assertNotContains(response, self.teacher.get_absolute_url())
        self.assertContains(response, self.school.get_absolute_url())
        self.assertContains(response, 'Добавить достижение')
        self.assertNotContains(response, 'Мои подопечные')


class UnrestrictedUsersTests(CabinetFixture):
    def test_editor_and_superuser_see_everything(self):
        superuser = User.objects.create_superuser('root', password='secret')
        for user in (make_editor(), superuser):
            self.client.force_login(user)
            for url in [*(reverse(name) for name in CLOSED_LISTS), self.colleague.get_absolute_url(),
                        self.foreign.get_absolute_url(), self.foreign_student.get_absolute_url()]:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.status(url), 200)


class CabinetQueryTests(TestCase):
    def count_queries(self, url):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_cabinets_do_not_query_per_row(self):
        teacher = make_teacher()
        self.client.force_login(make_teacher_user(teacher))

        def add_rows(count):
            for index in range(count):
                student = make_student(supervisor=teacher, last_name=f'Курсант{index}')
                make_adjunct(teacher, last_name=f'Адъюнкт{index}')
                publication = publication_by(f'Статья {index}', teacher=teacher)
                PublicationAuthor.objects.create(publication=publication, student=student, order=2)
                Task.objects.create(student=student, title=f'Задача {index}')

        add_rows(2)
        few = self.count_queries(teacher.get_absolute_url())
        add_rows(4)
        self.assertEqual(self.count_queries(teacher.get_absolute_url()), few)
