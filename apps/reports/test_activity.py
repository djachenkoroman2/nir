import datetime
from io import BytesIO
from urllib.parse import unquote

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from docx import Document

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .activity import (
    ADJUNCTS, ADMINS, EDITORS, OTHERS, STUDENTS, TEACHERS, UNKNOWN, build_activity_report, user_category,
)
from .docx_common import DOCX_TYPE

A = ActivityLog.Action
NOW = timezone.now()


def log(user, action, moment, username=None):
    return ActivityLog.objects.create(user=user, username=username or (user.username if user else ''),
                                      action=action, created_at=moment)


def rows(report):
    return {category.key: {row.username: row.values for row in category.rows} for category in report.categories}


class ActivityReportBuildTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', password='secret')
        self.editor = make_editor()
        self.teacher = make_teacher()
        self.teacher_user = make_teacher_user(self.teacher)
        self.adjunct_user = make_adjunct_user(make_adjunct(self.teacher))
        self.student_user = make_student_user(make_student(supervisor=self.teacher))
        self.reader = User.objects.create_user('reader', password='secret')
        self.start, self.end = NOW - datetime.timedelta(days=7), NOW

    def test_category_priority(self):
        # Суперпользователь с карточкой преподавателя — всё равно администратор; редактор с карточкой — редактор.
        make_teacher(last_name='Главный', user=self.root)
        editor_teacher = make_teacher(last_name='Редакторов', user=self.editor)
        self.assertEqual(user_category(User.objects.get(pk=self.root.pk)), ADMINS)
        self.assertEqual(user_category(User.objects.get(pk=self.editor.pk)), EDITORS)
        self.assertTrue(editor_teacher.user_id)
        expected = {self.teacher_user: TEACHERS, self.adjunct_user: ADJUNCTS, self.student_user: STUDENTS,
                    self.reader: OTHERS}
        for user, category in expected.items():
            with self.subTest(user=user.username):
                self.assertEqual(user_category(User.objects.get(pk=user.pk)), category)

    def test_counts_totals_and_unknown_logins(self):
        moment = NOW - datetime.timedelta(days=1)
        for action in (A.LOGIN, A.VIEW, A.VIEW, A.CREATE, A.UPDATE, A.DELETE, A.EXPORT, A.LOGOUT):
            log(self.teacher_user, action, moment)
        log(self.teacher_user, A.LOGIN_FAILED, moment)
        log(self.student_user, A.VIEW, moment)
        log(None, A.LOGIN_FAILED, moment, username='ghost')
        log(None, A.LOGIN_FAILED, moment, username='ghost')
        report = build_activity_report(self.start, self.end)
        data = rows(report)
        self.assertEqual(data[TEACHERS], {'teacher': [1, 1, 2, 1, 1, 1, 1]})
        self.assertEqual(data[STUDENTS], {'cadet': [0, 0, 1, 0, 0, 0, 0]})
        self.assertEqual(data[UNKNOWN], {'ghost': [0, 2, 0, 0, 0, 0, 0]})
        self.assertEqual(data[ADMINS], {})
        self.assertEqual(report.totals, [1, 3, 3, 1, 1, 1, 1])
        teachers = next(category for category in report.categories if category.key == TEACHERS)
        self.assertEqual(teachers.totals, [1, 1, 2, 1, 1, 1, 1])
        self.assertEqual(teachers.rows[0].last, moment)

    def test_period_boundaries_are_inclusive(self):
        log(self.reader, A.VIEW, self.start)
        log(self.reader, A.VIEW, self.end)
        log(self.reader, A.VIEW, self.start - datetime.timedelta(seconds=1))
        log(self.reader, A.VIEW, self.end + datetime.timedelta(seconds=1))
        self.assertEqual(rows(build_activity_report(self.start, self.end))[OTHERS]['reader'][2], 2)

    def test_category_filter_inactive_users_and_sorting(self):
        log(self.reader, A.VIEW, NOW - datetime.timedelta(days=2))
        log(self.editor, A.VIEW, NOW - datetime.timedelta(hours=1))
        report = build_activity_report(self.start, self.end, categories=[OTHERS])
        self.assertEqual([category.key for category in report.categories], [OTHERS])
        self.assertNotIn('teacher', rows(build_activity_report(self.start, self.end))[TEACHERS])
        everyone = rows(build_activity_report(self.start, self.end, show_inactive=True))
        self.assertEqual(everyone[TEACHERS]['teacher'], [0] * 7)
        other = User.objects.create_user('another')
        log(other, A.VIEW, NOW - datetime.timedelta(hours=1))
        ordered = [row.username for row in build_activity_report(self.start, self.end).categories[5].rows]
        self.assertEqual(ordered, ['another', 'reader'])


class ActivityReportViewTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', password='secret')
        self.teacher_user = make_teacher_user(make_teacher())
        log(self.teacher_user, A.LOGIN, NOW - datetime.timedelta(days=1))
        log(None, A.LOGIN_FAILED, NOW - datetime.timedelta(days=1), username='ghost')
        self.url = reverse('reports:activity')

    def test_access(self):
        holder = User.objects.create_user('auditor', password='secret')
        holder.user_permissions.add(Permission.objects.get(codename='view_activity_report'))
        for user in (self.root, holder):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(self.url).status_code, 200)
                self.assertContains(self.client.get(reverse('reports:report_list')), self.url)
        teacher = make_teacher(last_name='Руководителев')
        denied = [make_editor(), self.teacher_user, make_adjunct_user(make_adjunct(teacher)),
                  make_student_user(make_student(supervisor=teacher)), User.objects.create_user('reader')]
        for user in denied:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.get(self.url, {'format': 'docx'}).status_code, 403)
                self.assertEqual(self.client.get(reverse('reports:activity_name', args=['ghost'])).status_code, 403)
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f'{reverse("login")}?next={self.url}')

    def test_page_and_user_logs(self):
        self.client.force_login(self.root)
        response = self.client.get(self.url)
        self.assertContains(response, 'Преподаватели')
        self.assertContains(response, reverse('reports:activity_user', args=[self.teacher_user.pk]))
        self.assertContains(response, reverse('reports:activity_name', args=['ghost']))
        detail = self.client.get(reverse('reports:activity_user', args=[self.teacher_user.pk]))
        self.assertEqual([record.action for record in detail.context['records']], [A.LOGIN])
        filtered = self.client.get(reverse('reports:activity_user', args=[self.teacher_user.pk]), {
            'start': (NOW - datetime.timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
            'end': timezone.localtime(NOW + datetime.timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'),
            'action': A.VIEW,
        })
        self.assertEqual(list(filtered.context['records']), [])
        ghost = self.client.get(reverse('reports:activity_name', args=['ghost']))
        self.assertEqual([record.action for record in ghost.context['records']], [A.LOGIN_FAILED])

    def test_invalid_period(self):
        self.client.force_login(self.root)
        response = self.client.get(self.url, {'submitted': '1', 'start': '2026-10-10T10:00', 'end': '2026-10-01T10:00'})
        self.assertIsNone(response.context['report'])
        self.assertContains(response, 'Начало периода не может быть позже конца')

    def test_query_count_does_not_grow(self):
        self.client.force_login(self.root)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(self.url).status_code, 200)
            return len(queries)

        few = count()
        for index in range(6):
            user = make_teacher_user(make_teacher(last_name=f'Учитель{index}'), f'teacher{index}')
            log(user, A.VIEW, NOW - datetime.timedelta(hours=index + 1))
            log(None, A.LOGIN_FAILED, NOW - datetime.timedelta(hours=1), username=f'ghost{index}')
        self.assertEqual(count(), few)


class ActivityReportDocxTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser('root', password='secret')
        self.teacher_user = make_teacher_user(make_teacher())
        log(self.teacher_user, A.LOGIN, NOW - datetime.timedelta(days=1))
        log(self.teacher_user, A.VIEW, NOW - datetime.timedelta(days=20))
        self.client.force_login(self.root)

    def download(self, **params):
        return self.client.get(reverse('reports:activity'), {'format': 'docx', **params})

    @staticmethod
    def cells(response):
        table = Document(BytesIO(response.content)).tables[0]
        return [cell.text for row in table.rows for cell in row.cells]

    def test_response_and_content(self):
        response = self.download()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], DOCX_TYPE)
        start = timezone.localtime(NOW - datetime.timedelta(days=7))
        disposition = unquote(response['Content-Disposition'])
        self.assertIn(f'Активность_пользователей_{start:%d.%m.%Y}-', disposition)
        self.assertIn(f'filename="activity_{start:%Y%m%d}-', disposition)
        cells = self.cells(response)
        self.assertIn('Преподаватели', cells)
        self.assertIn('Итого: преподаватели', cells)
        self.assertIn('Всего', cells)
        self.assertTrue(any(cell.startswith('teacher') for cell in cells))
        self.assertTrue(ActivityLog.objects.filter(user=self.root, action=A.EXPORT).exists())

    def test_parameters_apply(self):
        start = timezone.localtime(NOW - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
        end = timezone.localtime(NOW).strftime('%Y-%m-%dT%H:%M')
        cells = self.cells(self.download(submitted='1', start=start, end=end, categories=[TEACHERS]))
        self.assertNotIn('Администраторы', cells)
        row = cells.index('Итого: преподаватели')
        self.assertEqual(cells[row + 1:row + 4], ['1', '0', '1'])  # входов, неудачных входов, просмотров
