import datetime
from unittest import mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.testing import formset_data
from apps.publications.forms import PublicationAuthorFormSet
from apps.publications.models import Publication, PublicationAuthor
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.staff.tests import make_editor, make_teacher
from apps.students.tests import make_student, make_teacher_user

from .models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment
from .study import academic_course


def make_adjunct(supervisor, **kwargs):
    defaults = {'last_name': 'Адъюнктов', 'first_name': 'Пётр', 'middle_name': 'Ильич',
                'dissertation_topic': 'Методы защиты информации', 'specialty': '2.3.6',
                'admission_year': timezone.localdate().year - 1, 'supervisor': supervisor}
    defaults.update(kwargs)
    return Adjunct.objects.create(**defaults)


def make_adjunct_user(adjunct, username='adjunct'):
    user = User.objects.create_user(username=username, password='secret')
    user.groups.add(Group.objects.get(name='Адъюнкты'))
    adjunct.user = user
    adjunct.save()
    return user


def make_task(adjunct, **kwargs):
    return Task.objects.create(adjunct=adjunct, title=kwargs.pop('title', 'Задача'), **kwargs)


class CourseTests(TestCase):
    def test_course_changes_on_september_first(self):
        self.assertEqual(academic_course(2025, datetime.date(2026, 8, 31)), 1)
        self.assertEqual(academic_course(2025, datetime.date(2026, 9, 1)), 2)
        self.assertEqual(academic_course(2025, datetime.date(2026, 10, 27)), 2)
        self.assertEqual(academic_course(2025, datetime.date(2025, 9, 1)), 1)

    def test_course_and_expired_term_on_model(self):
        teacher = make_teacher()
        with mock.patch('apps.adjuncts.study.timezone.localdate', return_value=datetime.date(2026, 10, 27)):
            adjunct = make_adjunct(teacher, admission_year=2024, study_years=3)
            self.assertEqual(adjunct.course, 3)
            self.assertFalse(adjunct.term_expired)
            adjunct.admission_year = 2023
            self.assertEqual(adjunct.course, 4)
            self.assertTrue(adjunct.term_expired)

    def test_no_course_for_finished_statuses(self):
        adjunct = make_adjunct(make_teacher())
        for status in (Adjunct.Status.GRADUATED, Adjunct.Status.DEFENDED, Adjunct.Status.EXPELLED):
            with self.subTest(status=status):
                adjunct.status = status
                self.assertIsNone(adjunct.course)
                self.assertFalse(adjunct.term_expired)
        adjunct.status = Adjunct.Status.ACADEMIC_LEAVE
        self.assertIsNotNone(adjunct.course)


class AuthorTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.adjunct = make_adjunct(self.teacher)
        self.publication = Publication.objects.create(title='Статья', year=2026)

    def test_exactly_one_of_four_author_kinds(self):
        from apps.students.tests import make_student
        student = make_student()
        cases = [
            ({'adjunct': self.adjunct}, True),
            ({'teacher': self.teacher, 'adjunct': self.adjunct}, False),
            ({'student': student, 'adjunct': self.adjunct}, False),
            ({'adjunct': self.adjunct, 'external_name': 'Внешний А. А.'}, False),
            ({}, False),
        ]
        for fields, valid in cases:
            with self.subTest(fields=list(fields)):
                author = PublicationAuthor(publication=self.publication, **fields)
                if valid:
                    author.full_clean()
                else:
                    with self.assertRaises(ValidationError):
                        author.full_clean()

    def test_formset_with_adjunct_and_duplicate_check(self):
        def formset(rows):
            return PublicationAuthorFormSet(formset_data('authors', rows), instance=self.publication)

        valid = formset([{'teacher': self.teacher.pk}, {'adjunct': self.adjunct.pk}])
        self.assertTrue(valid.is_valid(), valid.errors)
        valid.save()
        self.assertEqual([a.adjunct for a in self.publication.authors.all()], [None, self.adjunct])
        duplicate = formset([{'adjunct': self.adjunct.pk}, {'adjunct': self.adjunct.pk}])
        self.assertFalse(duplicate.is_valid())
        self.assertIn('Один и тот же адъюнкт указан несколько раз.', duplicate.non_form_errors())

    def test_expelled_adjunct_is_not_offered(self):
        expelled = make_adjunct(self.teacher, last_name='Отчисленный', status=Adjunct.Status.EXPELLED)
        form = PublicationAuthorFormSet(instance=self.publication).forms[0]
        self.assertNotIn(expelled, form.fields['adjunct'].queryset)
        self.assertIn(self.adjunct, form.fields['adjunct'].queryset)

    def test_account_cannot_belong_to_teacher_and_adjunct(self):
        user = User.objects.create_user(username='both')
        self.teacher.user = user
        self.teacher.save()
        self.adjunct.user = user
        with self.assertRaises(ValidationError):
            self.adjunct.full_clean()


class AdjunctAsAuthorTests(TestCase):
    """Адъюнкт ведёт свои публикации так же, как преподаватель."""

    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.adjunct = make_adjunct(self.supervisor)
        self.user = make_adjunct_user(self.adjunct)
        self.client.force_login(self.user)

    def data(self, authors, title='Статья адъюнкта'):
        data = {'kind': 'article', 'title': title, 'year': '2026'}
        data.update(formset_data('authors', authors))
        return data

    def test_create_form_is_prefilled_with_self(self):
        response = self.client.get(reverse('publications:publication_create'))
        self.assertEqual(response.context['formset'].forms[0].initial, {'adjunct': self.adjunct.pk})

    def test_creates_publication_with_self_and_cannot_remove_self(self):
        response = self.client.post(reverse('publications:publication_create'), self.data([{'adjunct': self.adjunct.pk}]))
        publication = Publication.objects.get(title='Статья адъюнкта')
        self.assertRedirects(response, publication.get_absolute_url())
        self.assertTrue(publication.is_authored_by(self.adjunct))

        response = self.client.post(reverse('publications:publication_create'),
                                    self.data([{'teacher': self.supervisor.pk}], title='Без себя'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Укажите среди авторов себя', str(response.context['formset'].non_form_errors()))
        self.assertFalse(Publication.objects.filter(title='Без себя').exists())

    def test_edits_only_own_publications(self):
        mine = Publication.objects.create(title='Моя', year=2026)
        PublicationAuthor.objects.create(publication=mine, adjunct=self.adjunct)
        foreign = Publication.objects.create(title='Чужая', year=2026)
        PublicationAuthor.objects.create(publication=foreign, teacher=self.supervisor)
        self.assertEqual(self.client.get(reverse('publications:publication_update', args=[mine.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('publications:publication_update', args=[foreign.pk])).status_code,
                         404)

    def test_teacher_with_same_pk_does_not_get_adjunct_records(self):
        # У преподавателя и адъюнкта могут совпасть первичные ключи: права не должны путаться.
        teacher = make_teacher(pk=500, last_name='Однофамильцев')
        adjunct = make_adjunct(self.supervisor, pk=500, last_name='Другой')
        publication = Publication.objects.create(title='Статья другого адъюнкта', year=2026)
        PublicationAuthor.objects.create(publication=publication, adjunct=adjunct)
        self.assertFalse(publication.is_authored_by(teacher))
        self.assertTrue(publication.is_authored_by(adjunct))
        self.assertFalse(adjunct.is_authored_by(teacher))


class AdjunctCardPermissionTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.other = make_teacher(last_name='Чужой')
        self.adjunct = make_adjunct(self.supervisor)
        self.update_url = reverse('adjuncts:adjunct_update', args=[self.adjunct.pk])
        self.contacts_url = reverse('adjuncts:adjunct_contacts', args=[self.adjunct.pk])

    def test_editor_and_supervisor_edit_card(self):
        self.client.force_login(make_editor())
        self.assertEqual(self.client.get(self.update_url).status_code, 200)
        self.client.force_login(make_teacher_user(self.supervisor))
        response = self.client.get(self.update_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('user', response.context['form'].fields)
        self.assertEqual(self.client.get(reverse('adjuncts:adjunct_create')).status_code, 403)

    def test_other_teacher_cannot_edit(self):
        self.client.force_login(make_teacher_user(self.other))
        self.assertEqual(self.client.get(self.update_url).status_code, 404)  # чужой адъюнкт в кабинете не виден

    def test_adjunct_changes_only_own_contacts(self):
        self.client.force_login(make_adjunct_user(self.adjunct))
        self.assertEqual(self.client.get(self.update_url).status_code, 403)
        response = self.client.post(self.contacts_url, {
            'email': 'me@example.com', 'phone': '123', 'dissertation_topic': 'Другая тема',
        })
        self.assertRedirects(response, self.adjunct.get_absolute_url())
        self.adjunct.refresh_from_db()
        self.assertEqual((self.adjunct.email, self.adjunct.phone), ('me@example.com', '123'))
        self.assertEqual(self.adjunct.dissertation_topic, 'Методы защиты информации')

        someone = make_adjunct(self.supervisor, last_name='Сосед')
        self.assertEqual(self.client.get(reverse('adjuncts:adjunct_contacts', args=[someone.pk])).status_code, 404)

    def test_adjunct_cannot_be_deleted_with_publications_or_defense(self):
        self.client.force_login(make_editor())
        publication = Publication.objects.create(title='Статья', year=2026)
        PublicationAuthor.objects.create(publication=publication, adjunct=self.adjunct)
        response = self.client.post(reverse('adjuncts:adjunct_delete', args=[self.adjunct.pk]), follow=True)
        self.assertContains(response, 'Нельзя удалить адъюнкта')
        self.assertTrue(Adjunct.objects.filter(pk=self.adjunct.pk).exists())

        publication.authors.all().delete()
        school = ScientificSchool.objects.create(name='Школа')
        DissertationDefense.objects.create(full_name='А', adjunct=self.adjunct, kind='candidate', title='Т',
                                           defense_date=datetime.date(2026, 1, 1), school=school)
        self.assertTrue(self.adjunct.has_protected_relations())

    def test_deleting_adjunct_removes_plan_tasks_achievements(self):
        self.client.force_login(make_editor())
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Экзамен', kind='exam',
                                 due_date=datetime.date(2026, 6, 1))
        make_task(self.adjunct)
        AdjunctAchievement.objects.create(adjunct=self.adjunct, kind='grant', level='national', title='Грант',
                                          result='победитель', date=datetime.date(2026, 3, 1))
        self.client.post(reverse('adjuncts:adjunct_delete', args=[self.adjunct.pk]))
        self.assertFalse(Adjunct.objects.exists())
        self.assertFalse(Task.objects.exists() or PlanStage.objects.exists() or AdjunctAchievement.objects.exists())

    def test_teacher_with_adjuncts_cannot_be_deleted(self):
        self.assertTrue(self.supervisor.has_protected_relations())


class PlanTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.adjunct = make_adjunct(self.supervisor, study_years=3)
        self.stage = PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Экзамен', kind='exam',
                                              due_date=datetime.date(2026, 6, 1))

    def test_study_year_cannot_exceed_term(self):
        stage = PlanStage(adjunct=self.adjunct, study_year=4, title='Лишний', kind='other',
                          due_date=datetime.date(2027, 6, 1))
        with self.assertRaises(ValidationError):
            stage.full_clean()

    def test_supervisor_manages_plan_adjunct_only_starts_stage(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        self.assertEqual(self.client.get(reverse('adjuncts:stage_create', args=[self.adjunct.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('adjuncts:stage_update', args=[self.stage.pk])).status_code, 200)

        self.client.force_login(make_adjunct_user(self.adjunct))
        self.assertEqual(self.client.get(reverse('adjuncts:stage_create', args=[self.adjunct.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('adjuncts:stage_update', args=[self.stage.pk])).status_code, 403)
        self.client.post(reverse('adjuncts:stage_start', args=[self.stage.pk]))
        self.stage.refresh_from_db()
        self.assertEqual(self.stage.status, PlanStage.Status.IN_PROGRESS)
        # Повторно (уже не «запланирован») — нельзя.
        self.assertEqual(self.client.post(reverse('adjuncts:stage_start', args=[self.stage.pk])).status_code, 403)

    def test_plan_percent_on_card(self):
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Статья', kind='publication',
                                 due_date=datetime.date(2026, 6, 30), status=PlanStage.Status.DONE)
        self.client.force_login(make_editor())
        response = self.client.get(self.adjunct.get_absolute_url())
        self.assertEqual((response.context['plan_done'], response.context['plan_percent']), (1, 50))


class TaskVisibilityTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.other_teacher = make_teacher(last_name='Чужой')
        self.adjunct = make_adjunct(self.supervisor)
        self.other_adjunct = make_adjunct(self.supervisor, last_name='Сосед')
        self.task = make_task(self.adjunct, title='Секретная задача')
        self.urls = [
            self.task.get_absolute_url(),
            reverse('tasks:task_update', args=[self.task.pk]),
            reverse('adjuncts:adjunct_tasks', args=[self.adjunct.pk]),
            reverse('adjuncts:task_create', args=[self.adjunct.pk]),
        ]

    def test_hidden_from_other_teacher_and_other_adjunct(self):
        for user in (make_teacher_user(self.other_teacher), make_adjunct_user(self.other_adjunct, 'neighbour')):
            self.client.force_login(user)
            for url in self.urls:
                with self.subTest(user=user.username, url=url):
                    # 404 — запись не видна; 403 — страницы нет в белом списке роли (адъюнкт не ставит задачи).
                    self.assertIn(self.client.get(url).status_code, (403, 404))
            # Карточка чужого адъюнкта в личном кабинете не видна вовсе.
            self.assertEqual(self.client.get(self.adjunct.get_absolute_url()).status_code, 404)
            self.assertNotContains(self.client.get(reverse('tasks:my_tasks')), 'Секретная задача')

    def test_visible_to_adjunct_supervisor_editor(self):
        users = [make_adjunct_user(self.adjunct), make_teacher_user(self.supervisor), make_editor()]
        for user in users:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertContains(self.client.get(self.task.get_absolute_url()), 'Секретная задача')
                self.assertContains(self.client.get(self.adjunct.get_absolute_url()), 'Секретная задача')
                self.assertContains(self.client.get(reverse('tasks:my_tasks')), 'Секретная задача')

    def test_adjunct_cannot_create_edit_or_delete_tasks(self):
        self.client.force_login(make_adjunct_user(self.adjunct))
        self.assertEqual(self.client.get(self.urls[1]).status_code, 403)
        self.assertEqual(self.client.get(self.urls[3]).status_code, 403)
        self.assertEqual(self.client.post(reverse('tasks:task_delete', args=[self.task.pk])).status_code, 403)

    def test_supervisor_creates_task(self):
        user = make_teacher_user(self.supervisor)
        self.client.force_login(user)
        response = self.client.post(self.urls[3], {'title': 'Новая', 'priority': 3, 'due_date': '2026-12-01'})
        task = Task.objects.get(title='Новая')
        self.assertRedirects(response, task.get_absolute_url())
        self.assertEqual((task.adjunct, task.created_by, task.status), (self.adjunct, user, Task.Status.NEW))

    def test_plan_stage_of_other_adjunct_is_rejected(self):
        foreign_stage = PlanStage.objects.create(adjunct=self.other_adjunct, study_year=1, title='Чужой этап',
                                                 kind='exam', due_date=datetime.date(2026, 6, 1))
        self.client.force_login(make_teacher_user(self.supervisor))
        response = self.client.post(self.urls[3], {'title': 'С этапом', 'priority': 2, 'plan_stage': foreign_stage.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title='С этапом').exists())


class TaskStatusTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев', first_name='Сергей', middle_name='Петрович')
        self.adjunct = make_adjunct(self.supervisor)
        self.adjunct_user = make_adjunct_user(self.adjunct)
        self.supervisor_user = make_teacher_user(self.supervisor)
        self.task = make_task(self.adjunct)
        self.url = reverse('tasks:task_status', args=[self.task.pk])

    def move(self, status):
        response = self.client.post(self.url, {'status': status})
        self.task.refresh_from_db()
        return response.status_code

    def test_adjunct_moves_along_chain_only(self):
        self.client.force_login(self.adjunct_user)
        self.assertEqual(self.move('review'), 403)  # перескочить «в работе» нельзя
        self.assertEqual(self.move('in_progress'), 302)
        self.assertEqual(self.move('done'), 403)  # приёмка — только руководителем
        self.assertEqual(self.move('review'), 302)
        self.assertEqual(self.move('in_progress'), 302)  # вернуть с проверки в работу можно
        self.assertEqual(self.move('cancelled'), 403)
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)

    def test_supervisor_moves_to_any_status_and_completion_date(self):
        self.client.force_login(self.supervisor_user)
        self.assertEqual(self.move('done'), 302)
        self.assertIsNotNone(self.task.completed_at)
        self.assertEqual(self.move('in_progress'), 302)
        self.assertIsNone(self.task.completed_at)
        self.assertEqual(self.move('cancelled'), 302)
        self.assertEqual(self.move('cancelled'), 403)  # в тот же статус — не переход

    def test_status_change_adds_system_comment(self):
        self.client.force_login(self.adjunct_user)
        self.move('in_progress')
        comment = self.task.comments.get()
        self.assertTrue(comment.is_system)
        self.assertEqual(comment.author, self.adjunct_user)
        self.assertEqual(comment.text, 'Смена статуса: новая → в работе')
        response = self.client.get(self.task.get_absolute_url())
        self.assertContains(response, 'Адъюнктов П. И.')
        self.assertContains(response, 'Смена статуса: новая → в работе')

    def test_buttons_show_only_allowed_transitions(self):
        self.client.force_login(self.adjunct_user)
        response = self.client.get(self.task.get_absolute_url())
        self.assertEqual([value for value, _ in response.context['transitions']], ['in_progress'])

    def test_overdue(self):
        today = timezone.localdate()
        self.assertFalse(make_task(self.adjunct).is_overdue)  # без срока
        late = make_task(self.adjunct, due_date=today - datetime.timedelta(days=1))
        self.assertTrue(late.is_overdue)
        self.assertFalse(make_task(self.adjunct, due_date=today).is_overdue)
        late.set_status(Task.Status.DONE)
        self.assertFalse(late.is_overdue)


class CommentTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.adjunct = make_adjunct(self.supervisor)
        self.adjunct_user = make_adjunct_user(self.adjunct)
        self.task = make_task(self.adjunct)

    def test_add_and_delete_own_comment_within_15_minutes(self):
        self.client.force_login(self.adjunct_user)
        self.client.post(self.task.get_absolute_url(), {'text': 'Вопрос по задаче'})
        comment = self.task.comments.get()
        self.assertEqual((comment.author, comment.text), (self.adjunct_user, 'Вопрос по задаче'))

        old = TaskComment.objects.create(task=self.task, author=self.adjunct_user, text='Старый',
                                         created_at=timezone.now() - datetime.timedelta(minutes=16))
        self.assertEqual(self.client.post(reverse('tasks:comment_delete', args=[old.pk])).status_code, 403)
        self.client.post(reverse('tasks:comment_delete', args=[comment.pk]))
        self.assertFalse(TaskComment.objects.filter(pk=comment.pk).exists())

    def test_cannot_delete_others_or_system_comment(self):
        supervisor_user = make_teacher_user(self.supervisor)
        theirs = TaskComment.objects.create(task=self.task, author=supervisor_user, text='Руководитель')
        system = TaskComment.objects.create(task=self.task, author=self.adjunct_user, text='Статус', is_system=True)
        self.client.force_login(self.adjunct_user)
        for comment in (theirs, system):
            with self.subTest(text=comment.text):
                self.assertEqual(self.client.post(reverse('tasks:comment_delete', args=[comment.pk])).status_code, 403)

    def test_empty_comment_is_rejected(self):
        self.client.force_login(self.adjunct_user)
        response = self.client.post(self.task.get_absolute_url(), {'text': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.task.comments.exists())


class MenuAndCabinetTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.adjunct = make_adjunct(self.supervisor)
        self.adjunct_user = make_adjunct_user(self.adjunct)
        self.supervisor_user = make_teacher_user(self.supervisor)
        make_task(self.adjunct, title='Новая 1')
        make_task(self.adjunct, title='Новая 2')
        make_task(self.adjunct, title='На проверке', status=Task.Status.REVIEW)

    def test_counter_in_header(self):
        self.client.force_login(self.adjunct_user)
        self.assertEqual(self.client.get('/', follow=True).context['task_menu']['attention'], 2)
        self.client.force_login(self.supervisor_user)
        self.assertEqual(self.client.get('/', follow=True).context['task_menu']['attention'], 1)
        self.client.force_login(User.objects.create_user(username='reader'))
        self.assertFalse(self.client.get('/', follow=True).context['task_menu']['show'])

    def test_adjunct_cabinet_is_own_card(self):
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Ближайший этап', kind='exam',
                                 due_date=timezone.localdate() + datetime.timedelta(days=10))
        self.client.force_login(self.adjunct_user)
        self.assertRedirects(self.client.get('/'), self.adjunct.get_absolute_url())
        response = self.client.get(self.adjunct.get_absolute_url())
        self.assertContains(response, 'Ближайший этап')
        self.assertContains(response, 'Новая 1')
        self.assertContains(response, 'Добавить публикацию')

    def test_teacher_card_shows_review_count_only_to_supervisor(self):
        self.client.force_login(self.supervisor_user)
        response = self.client.get(self.supervisor.get_absolute_url())
        self.assertTrue(response.context['show_review_counts'])
        self.assertContains(response, 'Научное руководство адъюнктами')
        self.client.force_login(User.objects.create_user(username='reader'))
        self.assertFalse(self.client.get(self.supervisor.get_absolute_url()).context['show_review_counts'])


class QueryCountTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.client.force_login(make_editor())

    def add_adjuncts(self, count):
        for index in range(count):
            adjunct = make_adjunct(self.supervisor, last_name=f'Адъюнкт{index}')
            make_task(adjunct)
            publication = Publication.objects.create(title=f'Статья {index}', year=2026)
            PublicationAuthor.objects.create(publication=publication, adjunct=adjunct)

    def count_queries(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_lists_do_not_query_per_row(self):
        for url in (reverse('adjuncts:adjunct_list'), reverse('tasks:my_tasks')):
            with self.subTest(url=url):
                self.add_adjuncts(2)
                few = self.count_queries(url)
                self.add_adjuncts(5)
                self.assertEqual(self.count_queries(url), few)

    def test_list_shows_course_counts_and_filters(self):
        self.add_adjuncts(1)
        make_adjunct(self.supervisor, last_name='Защитившийся', status=Adjunct.Status.DEFENDED)
        response = self.client.get(reverse('adjuncts:adjunct_list'))
        row = response.context['adjunct_list'][0]
        self.assertEqual((row.publication_count, row.open_task_count, row.show_tasks), (1, 1, True))
        self.assertNotIn('Защитившийся', [a.last_name for a in response.context['adjunct_list']])
        response = self.client.get(reverse('adjuncts:adjunct_list'), {'status': 'defended'})
        self.assertEqual([a.last_name for a in response.context['adjunct_list']], ['Защитившийся'])


def make_student_task(student, **kwargs):
    return Task.objects.create(student=student, title=kwargs.pop('title', 'Задача курсанта'), **kwargs)


class StudentTaskModelTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.adjunct = make_adjunct(self.supervisor)
        self.student = make_student(supervisor=self.supervisor)

    def test_exactly_one_assignee(self):
        for fields in ({}, {'adjunct': self.adjunct, 'student': self.student}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Task(title='Задача', **fields).full_clean()
        Task(title='Задача', student=self.student).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Task.objects.create(title='Без исполнителя')

    def test_student_task_has_no_plan_stage_and_review(self):
        stage = PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Экзамен', kind='exam',
                                         due_date=timezone.localdate())
        with self.assertRaises(ValidationError) as error:
            Task(title='Задача', student=self.student, plan_stage=stage).full_clean()
        self.assertIn('plan_stage', error.exception.message_dict)
        with self.assertRaises(ValidationError) as error:
            Task(title='Задача', student=self.student, status=Task.Status.REVIEW).full_clean()
        self.assertIn('status', error.exception.message_dict)

    def test_person_and_links(self):
        task = make_student_task(self.student)
        self.assertEqual(task.person, self.student)
        self.assertTrue(task.is_supervised_by(self.supervisor))
        self.assertFalse(task.is_authored_by(self.adjunct))

    def test_deleting_student_removes_tasks(self):
        task = make_student_task(self.student)
        TaskComment.objects.create(task=task, text='Заметка')
        self.student.delete()
        self.assertFalse(Task.objects.exists())
        self.assertFalse(TaskComment.objects.exists())


class StudentTaskVisibilityTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.student = make_student(supervisor=self.supervisor)
        self.task = make_student_task(self.student, title='Задача курсанта')
        self.urls = [
            self.task.get_absolute_url(),
            reverse('tasks:task_update', args=[self.task.pk]),
            reverse('students:student_tasks', args=[self.student.pk]),
            reverse('students:task_create', args=[self.student.pk]),
        ]

    def test_hidden_from_other_teacher_and_adjunct(self):
        other_teacher_user = make_teacher_user(make_teacher(last_name='Чужой'))
        adjunct_user = make_adjunct_user(make_adjunct(self.supervisor))
        for user in (other_teacher_user, adjunct_user):
            self.client.force_login(user)
            for url in self.urls:
                with self.subTest(user=user.username, url=url):
                    # 404 — запись не видна; 403 — страницы нет в белом списке роли (адъюнкт не ставит задачи).
                    self.assertIn(self.client.get(url).status_code, (403, 404))
            # Карточка чужого курсанта в личном кабинете не видна вовсе.
            self.assertIn(self.client.get(self.student.get_absolute_url()).status_code, (403, 404))
            self.assertNotContains(self.client.get(reverse('tasks:my_tasks')), 'Задача курсанта')

    def test_supervisor_and_editor_see_and_manage(self):
        for user in (make_teacher_user(self.supervisor), make_editor()):
            self.client.force_login(user)
            for url in self.urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
            card = self.client.get(self.student.get_absolute_url())
            self.assertContains(card, 'Задача курсанта')
            self.assertContains(card, 'Поставить задачу')

    def test_student_without_supervisor_only_for_editors(self):
        self.student.supervisor = None
        self.student.save()
        self.client.force_login(make_teacher_user(self.supervisor))
        self.assertEqual(self.client.get(self.task.get_absolute_url()).status_code, 404)
        self.client.force_login(make_editor())
        self.assertEqual(self.client.get(self.task.get_absolute_url()).status_code, 200)

    def test_new_supervisor_sees_tasks(self):
        new_supervisor = make_teacher(last_name='Новый')
        self.student.supervisor = new_supervisor
        self.student.save()
        self.client.force_login(make_teacher_user(new_supervisor))
        self.assertEqual(self.client.get(self.task.get_absolute_url()).status_code, 200)

    def test_supervisor_creates_task_without_plan_stage(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        url = reverse('students:task_create', args=[self.student.pk])
        self.assertNotIn('plan_stage', self.client.get(url).context['form'].fields)
        response = self.client.post(url, {'title': 'Подготовить тезисы', 'priority': Task.Priority.HIGH})
        task = Task.objects.get(title='Подготовить тезисы')
        self.assertRedirects(response, task.get_absolute_url())
        self.assertEqual((task.student, task.adjunct, task.created_by.username), (self.student, None, 'teacher'))

    def test_delete_redirects_to_student_tasks(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        response = self.client.post(reverse('tasks:task_delete', args=[self.task.pk]))
        self.assertRedirects(response, reverse('students:student_tasks', args=[self.student.pk]))


class StudentTaskStatusTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.supervisor_user = make_teacher_user(self.supervisor)
        self.task = make_student_task(make_student(supervisor=self.supervisor))
        self.client.force_login(self.supervisor_user)

    def change(self, status):
        return self.client.post(reverse('tasks:task_status', args=[self.task.pk]), {'status': status})

    def test_review_is_not_available(self):
        response = self.client.get(self.task.get_absolute_url())
        values = [value for value, _ in response.context['transitions']]
        self.assertEqual(values, [Task.Status.IN_PROGRESS, Task.Status.DONE, Task.Status.CANCELLED])
        self.assertEqual(self.change(Task.Status.REVIEW).status_code, 403)

    def test_done_sets_completion_date_and_adds_system_comment(self):
        self.change(Task.Status.DONE)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.DONE)
        self.assertIsNotNone(self.task.completed_at)
        comment = self.task.comments.get()
        self.assertTrue(comment.is_system)
        self.assertEqual(comment.text, 'Смена статуса: новая → выполнена')

    def test_status_filter_has_no_review(self):
        response = self.client.get(reverse('students:student_tasks', args=[self.task.student_id]))
        self.assertNotIn(Task.Status.REVIEW, [value for value, _ in response.context['status_choices']])


class MixedTasksTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.supervisor_user = make_teacher_user(self.supervisor)
        self.adjunct = make_adjunct(self.supervisor)
        self.student = make_student(supervisor=self.supervisor)
        self.yesterday = timezone.localdate() - datetime.timedelta(days=1)
        make_task(self.adjunct, title='Задача адъюнкта', status=Task.Status.REVIEW)
        make_student_task(self.student, title='Просроченная задача курсанта', due_date=self.yesterday)
        make_student_task(self.student, title='Задача курсанта в срок')

    def titles(self, **params):
        response = self.client.get(reverse('tasks:my_tasks'), params)
        return {task.title for task in response.context['tasks']}

    def test_my_tasks_shows_adjuncts_and_students_with_kind_filter(self):
        self.client.force_login(self.supervisor_user)
        everything = {'Задача адъюнкта', 'Просроченная задача курсанта', 'Задача курсанта в срок'}
        self.assertEqual(self.titles(), everything)
        self.assertEqual(self.titles(kind='adjuncts'), {'Задача адъюнкта'})
        self.assertEqual(self.titles(kind='students'), everything - {'Задача адъюнкта'})
        self.assertEqual(self.titles(student=self.student.pk), everything - {'Задача адъюнкта'})
        self.assertEqual(self.titles(kind='unknown'), everything)
        response = self.client.get(reverse('tasks:my_tasks'))
        self.assertContains(response, 'курсант</span>')
        self.assertContains(response, 'name="kind"')

    def test_counter_counts_review_and_overdue_student_tasks(self):
        Task.objects.create(student=self.student, title='Выполненная просроченная', due_date=self.yesterday,
                            status=Task.Status.DONE)
        self.client.force_login(self.supervisor_user)
        menu = self.client.get('/', follow=True).context['task_menu']
        self.assertEqual(menu['attention'], 2)
        self.assertIn('курсантов', menu['title'])

    def test_menu_for_teacher_with_students_only(self):
        teacher = make_teacher(last_name='Безадъюнктов')
        make_student(supervisor=teacher, last_name='Подопечный')
        self.client.force_login(make_teacher_user(teacher, 'only_students'))
        self.assertTrue(self.client.get('/', follow=True).context['task_menu']['show'])

    def test_student_list_and_teacher_card_show_open_tasks_to_supervisor_only(self):
        # Список курсантов в личном кабинете закрыт — число задач в нём видит редактор.
        self.client.force_login(make_editor())
        response = self.client.get(reverse('students:student_list'))
        row = response.context['student_list'][0]
        self.assertEqual((row.open_task_count, row.show_tasks), (2, True))
        self.client.force_login(self.supervisor_user)
        card = self.client.get(self.supervisor.get_absolute_url())
        self.assertEqual(card.context['supervised_students'][0].open_task_count, 2)
        self.client.force_login(User.objects.create_user(username='reader'))
        response = self.client.get(reverse('students:student_list'))
        self.assertFalse(response.context['show_task_column'])

    def test_student_task_page_breadcrumbs(self):
        task = Task.objects.get(title='Задача курсанта в срок')
        self.client.force_login(self.supervisor_user)
        response = self.client.get(task.get_absolute_url())
        self.assertContains(response, reverse('students:student_list'))
        self.assertContains(response, reverse('students:student_tasks', args=[self.student.pk]))
        self.assertContains(response, '<dt class="col-sm-3">Курсант</dt>', html=False)


class MixedQueryCountTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher()
        self.client.force_login(make_teacher_user(self.supervisor))

    def add_rows(self, count):
        for index in range(count):
            make_task(make_adjunct(self.supervisor, last_name=f'Адъюнкт{index}'))
            make_student_task(make_student(supervisor=self.supervisor, last_name=f'Курсант{index}'))

    def count_queries(self, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_lists_do_not_query_per_row(self):
        # Кабинет руководителя (его карточка с подопечными) и «Мои задачи».
        for url in (self.supervisor.get_absolute_url(), reverse('tasks:my_tasks')):
            with self.subTest(url=url):
                self.add_rows(2)
                few = self.count_queries(url)
                self.add_rows(4)
                self.assertEqual(self.count_queries(url), few)
