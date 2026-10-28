"""Личный кабинет курсанта: учётная запись, белый список страниц, портфолио и задачи."""
import datetime

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.adjuncts.models import Task, TaskComment
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.core.permissions import get_person
from apps.core.testing import formset_data
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.tests import make_editor, make_teacher

from .cabinet import ALLOWED_URLS
from .models import StudentAchievement
from .tests import make_achievement, make_student, make_teacher_user


def make_student_user(student, username='cadet'):
    user = User.objects.create_user(username=username, password='secret')
    user.groups.add(Group.objects.get(name='Курсанты'))
    student.user = user
    student.save()
    return user


def named_urls_without_arguments(resolver=None, namespace=''):
    """Имена всех URL проекта, которые не принимают параметров (для проверки «закрыто по умолчанию»)."""
    resolver = resolver or get_resolver()
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            prefix = f'{namespace}{pattern.namespace}:' if pattern.namespace else namespace
            if not pattern.pattern.converters and '(?P<' not in str(pattern.pattern):
                yield from named_urls_without_arguments(pattern, prefix)
        elif isinstance(pattern, URLPattern) and pattern.name:
            if not pattern.pattern.converters and '(?P<' not in str(pattern.pattern):
                yield f'{namespace}{pattern.name}'


class CabinetTestCase(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.student = make_student(supervisor=self.supervisor)
        self.user = make_student_user(self.student)
        self.other = make_student(last_name='Сосед', supervisor=self.supervisor)
        self.client.force_login(self.user)

    def get(self, name, *args):
        return self.client.get(reverse(name, args=args))


class AccountTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student(supervisor=self.teacher)

    def test_get_person_returns_student(self):
        user = make_student_user(self.student)
        self.assertEqual(get_person(user), self.student)

    def test_account_belongs_to_one_person(self):
        teacher_user = make_teacher_user(self.teacher)
        self.student.user = teacher_user
        with self.assertRaisesMessage(ValidationError, 'преподавателя'):
            self.student.full_clean()

        student_user = make_student_user(make_student(last_name='Другой'), 'other_cadet')
        adjunct = make_adjunct(self.teacher)
        adjunct.user = student_user
        with self.assertRaisesMessage(ValidationError, 'курсанта'):
            adjunct.full_clean()
        teacher = make_teacher(last_name='Новый')
        teacher.user = User.objects.get(pk=student_user.pk)  # без кэша связи, заполненного присваиванием выше
        with self.assertRaisesMessage(ValidationError, 'курсанта'):
            teacher.full_clean()

    def test_student_and_teacher_with_same_pk_are_different_people(self):
        teacher = make_teacher(pk=700, last_name='Однофамильцев')
        student = make_student(pk=700, last_name='Тёзкин')
        publication = Publication.objects.create(title='Статья преподавателя', year=2026)
        PublicationAuthor.objects.create(publication=publication, teacher=teacher)
        self.assertFalse(publication.is_authored_by(student))
        self.assertFalse(student.is_authored_by(teacher))
        adjunct = make_adjunct(self.teacher, pk=700)
        self.assertFalse(student.is_authored_by(adjunct))
        self.assertTrue(student.is_authored_by(student))


class WhitelistTests(CabinetTestCase):
    def test_closed_pages_of_every_section(self):
        foreign_publication = Publication.objects.create(title='Чужая', year=2026)
        conference = Conference.objects.create(title='Конференция', level='national', start_date='2026-05-01')
        closed = {
            'staff:teacher_list': 403, 'research:project_list': 403, 'publications:publication_list': 403,
            'ip:ip_list': 403, 'ip:ip_create': 403, 'conferences:conference_list': 403,
            'schools:school_list': 403, 'students:student_list': 403, 'students:student_create': 403,
            'adjuncts:adjunct_list': 403, 'admin:index': 403,
        }
        for name, status in closed.items():
            with self.subTest(name=name):
                self.assertEqual(self.get(name).status_code, status)
        with_args = [
            ('staff:teacher_detail', self.supervisor.pk), ('students:student_detail', self.other.pk),
            ('students:student_update', self.student.pk), ('students:student_tasks', self.other.pk),
            ('publications:publication_detail', foreign_publication.pk),
            ('conferences:conference_detail', conference.pk),
        ]
        for name, pk in with_args:
            with self.subTest(name=name):
                self.assertIn(self.get(name, pk).status_code, (403, 404))

    def test_pages_not_in_whitelist_are_closed_by_default(self):
        names = set(named_urls_without_arguments())
        self.assertIn('staff:teacher_list', names)
        for name in sorted(names - set(ALLOWED_URLS)):
            with self.subTest(name=name):
                self.assertEqual(self.get(name).status_code, 403)

    def test_header_has_only_cabinet_items(self):
        response = self.get('students:student_detail', self.student.pk)
        self.assertContains(response, 'Мой кабинет')
        self.assertContains(response, 'Мои задачи')
        for name in ('staff:teacher_list', 'publications:publication_list', 'students:student_list', 'admin:index'):
            with self.subTest(name=name):
                self.assertNotContains(response, f'href="{reverse(name)}"')

    def test_home_is_own_card(self):
        self.assertRedirects(self.client.get('/'), self.student.get_absolute_url())
        response = self.get('students:student_detail', self.student.pk)
        self.assertTrue(response.context['is_cabinet'])
        self.assertContains(response, 'Добавить публикацию')
        # Руководитель — без ссылки на закрытую карточку преподавателя.
        self.assertNotContains(response, self.supervisor.get_absolute_url())

    def test_other_users_are_not_restricted(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        self.assertEqual(self.get('students:student_list').status_code, 200)
        self.assertEqual(self.get('students:student_detail', self.student.pk).status_code, 200)


class PortfolioTests(CabinetTestCase):
    def data(self, authors, title='Статья курсанта'):
        data = {'kind': 'article', 'title': title, 'year': '2026'}
        data.update(formset_data('authors', authors))
        return data

    def test_adds_publication_with_self_and_cannot_remove_self(self):
        response = self.get('publications:publication_create')
        self.assertEqual(response.context['formset'].forms[0].initial, {'student': self.student.pk})
        response = self.client.post(reverse('publications:publication_create'),
                                    self.data([{'student': self.student.pk}, {'teacher': self.supervisor.pk}]))
        publication = Publication.objects.get(title='Статья курсанта')
        self.assertRedirects(response, publication.get_absolute_url())
        self.assertTrue(publication.is_authored_by(self.student))

        response = self.client.post(reverse('publications:publication_create'),
                                    self.data([{'teacher': self.supervisor.pk}], title='Без себя'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Publication.objects.filter(title='Без себя').exists())

    def test_own_and_foreign_publications(self):
        mine = Publication.objects.create(title='Моя', year=2026)
        PublicationAuthor.objects.create(publication=mine, student=self.student)
        foreign = Publication.objects.create(title='Чужая', year=2026)
        PublicationAuthor.objects.create(publication=foreign, student=self.other)
        for name in ('publications:publication_detail', 'publications:publication_update',
                     'publications:publication_delete'):
            with self.subTest(name=name):
                self.assertEqual(self.get(name, mine.pk).status_code, 200)
                self.assertEqual(self.get(name, foreign.pk).status_code, 404)

    def test_after_deleting_publication_goes_to_cabinet(self):
        mine = Publication.objects.create(title='Моя', year=2026)
        PublicationAuthor.objects.create(publication=mine, student=self.student)
        response = self.client.post(reverse('publications:publication_delete', args=[mine.pk]))
        self.assertRedirects(response, reverse('core:home'), target_status_code=302)
        self.assertFalse(Publication.objects.exists())

    def test_ip_only_viewed_when_coauthor(self):
        ip = IntellectualProperty.objects.create(title='Программа', kind='software', number='1',
                                                 registration_date='2026-02-01')
        IntellectualPropertyAuthor.objects.create(intellectual_property=ip, student=self.student)
        self.assertEqual(self.get('ip:ip_detail', ip.pk).status_code, 200)
        self.assertEqual(self.get('ip:ip_update', ip.pk).status_code, 403)
        IntellectualPropertyAuthor.objects.filter(intellectual_property=ip).delete()
        self.assertEqual(self.get('ip:ip_detail', ip.pk).status_code, 404)

    def test_adds_report_through_conference_choice(self):
        conference = Conference.objects.create(title='Конференция', level='national', start_date='2026-05-01')
        foreign_publication = Publication.objects.create(title='Чужая свободная', year=2026)
        response = self.client.post(reverse('conferences:report_choose'), {'conference': conference.pk})
        self.assertRedirects(response, reverse('conferences:report_create', args=[conference.pk]))
        response = self.get('conferences:report_create', conference.pk)
        self.assertNotIn(foreign_publication, response.context['form'].fields['publication'].queryset)
        data = {'title': 'Мой доклад', 'form': 'section'}
        data.update(formset_data('speakers', [{'student': self.student.pk}]))
        response = self.client.post(reverse('conferences:report_create', args=[conference.pk]), data)
        self.assertRedirects(response, conference.get_absolute_url())
        report = Report.objects.get(title='Мой доклад')
        self.assertTrue(report.is_authored_by(self.student))
        self.assertEqual(self.get('conferences:report_update', report.pk).status_code, 200)

        foreign = Report.objects.create(conference=conference, title='Чужой доклад')
        ReportSpeaker.objects.create(report=foreign, teacher=self.supervisor)
        self.assertEqual(self.get('conferences:report_update', foreign.pk).status_code, 404)

    def test_new_conference_leads_to_report_form(self):
        data = {'title': 'Студенческая весна', 'level': 'university', 'start_date': '2026-04-10'}
        response = self.client.post(reverse('conferences:conference_create') + '?then=report', data)
        conference = Conference.objects.get(title='Студенческая весна')
        self.assertRedirects(response, reverse('conferences:report_create', args=[conference.pk]))

    def test_manages_own_achievements_only(self):
        response = self.get('students:achievement_create', self.student.pk)
        self.assertNotIn('student', response.context['form'].fields)
        self.assertEqual(response.context['form'].initial['supervisor'], self.supervisor)
        data = {'kind': 'olympiad', 'level': 'university', 'title': 'Олимпиада', 'result': 'призёр',
                'date': '2026-03-01', 'supervisor': self.supervisor.pk}
        response = self.client.post(reverse('students:achievement_create', args=[self.student.pk]), data)
        self.assertRedirects(response, self.student.get_absolute_url())
        mine = StudentAchievement.objects.get(student=self.student)
        foreign = make_achievement(self.other)
        self.assertEqual(self.get('students:achievement_update', mine.pk).status_code, 200)
        self.assertEqual(self.get('students:achievement_update', foreign.pk).status_code, 404)
        self.assertEqual(self.get('students:achievement_create', self.other.pk).status_code, 404)
        self.client.post(reverse('students:achievement_delete', args=[mine.pk]))
        self.assertFalse(StudentAchievement.objects.filter(pk=mine.pk).exists())


class CabinetTaskTests(CabinetTestCase):
    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(student=self.student, title='Моя задача')
        self.foreign = Task.objects.create(student=self.other, title='Чужая задача')

    def change(self, status):
        return self.client.post(reverse('tasks:task_status', args=[self.task.pk]), {'status': status})

    def test_sees_own_tasks_only(self):
        self.assertContains(self.get('tasks:task_detail', self.task.pk), 'Моя задача')
        self.assertEqual(self.get('tasks:task_detail', self.foreign.pk).status_code, 404)
        self.assertEqual(self.get('students:student_tasks', self.student.pk).status_code, 200)
        my_tasks = self.get('tasks:my_tasks')
        self.assertContains(my_tasks, 'Моя задача')
        self.assertNotContains(my_tasks, 'Чужая задача')
        self.assertEqual(self.get('tasks:task_update', self.task.pk).status_code, 403)
        self.assertEqual(self.get('students:task_create', self.student.pk).status_code, 403)

    def test_moves_along_chain_and_cannot_accept(self):
        self.assertEqual(self.change(Task.Status.DONE).status_code, 403)
        self.change(Task.Status.IN_PROGRESS)
        self.change(Task.Status.REVIEW)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.REVIEW)
        self.assertEqual(self.task.comments.filter(is_system=True, author=self.user).count(), 2)
        self.assertEqual(self.change(Task.Status.DONE).status_code, 403)
        self.client.post(reverse('tasks:task_detail', args=[self.task.pk]), {'text': 'Готово, посмотрите'})
        self.assertTrue(TaskComment.objects.filter(task=self.task, author=self.user, is_system=False).exists())

    def test_review_only_for_student_with_account(self):
        self.assertIn(Task.Status.REVIEW, self.task.statuses)
        self.assertNotIn(Task.Status.REVIEW, Task.statuses_for(make_student(last_name='Без входа')))

    def test_header_counters(self):
        self.assertEqual(self.client.get(self.student.get_absolute_url()).context['task_menu']['attention'], 1)
        supervisor_user = make_teacher_user(self.supervisor)
        self.task.set_status(Task.Status.REVIEW)
        self.task.save()
        # Просрочка задачи курсанта с учётной записью руководителю не сигналит: курсант сам ведёт задачу.
        Task.objects.create(student=self.student, title='Просроченная', status=Task.Status.IN_PROGRESS,
                            due_date=timezone.localdate() - datetime.timedelta(days=3))
        self.client.force_login(supervisor_user)
        self.assertEqual(self.client.get('/').context['task_menu']['attention'], 1)

    def test_supervisor_and_editor_still_manage(self):
        for user in (make_teacher_user(self.supervisor), make_editor()):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.get('tasks:task_update', self.task.pk).status_code, 200)
                self.assertEqual(self.get('students:student_detail', self.student.pk).status_code, 200)

    def test_adjunct_does_not_see_student_tasks(self):
        self.client.force_login(make_adjunct_user(make_adjunct(self.supervisor)))
        self.assertEqual(self.get('tasks:task_detail', self.task.pk).status_code, 404)


class StudentQueryTests(TestCase):
    def test_person_is_loaded_with_user(self):
        student = make_student(supervisor=make_teacher())
        self.client.force_login(make_student_user(student))
        # Карточка приходит вместе с пользователем (PersonModelBackend): get_person больше не ходит в базу.
        response = self.client.get(student.get_absolute_url())
        user = response.wsgi_request.user
        with self.assertNumQueries(0):
            self.assertEqual(get_person(user), student)
