import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.conferences.models import Conference
from apps.core.testing import formset_data
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.tests import make_editor, make_teacher
from apps.students.tests import make_teacher_user

from .models import ActivityLog

A = ActivityLog.Action


def actions():
    return list(ActivityLog.objects.order_by('pk').values_list('action', flat=True))


class AuthLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('reader', password='secret-pass')

    def test_login_logout_and_failed_login(self):
        self.client.post(reverse('login'), {'username': 'reader', 'password': 'secret-pass'})
        self.client.post(reverse('logout'))
        self.client.post(reverse('login'), {'username': 'reader', 'password': 'wrong-pass'})
        self.client.post(reverse('login'), {'username': 'nobody', 'password': 'other-pass'})
        records = list(ActivityLog.objects.order_by('pk'))
        self.assertEqual([record.action for record in records], [A.LOGIN, A.LOGOUT, A.LOGIN_FAILED, A.LOGIN_FAILED])
        self.assertEqual(records[2].user, self.user)
        self.assertEqual((records[3].user, records[3].username), (None, 'nobody'))
        self.assertEqual(records[0].ip, '127.0.0.1')
        # Пароли не сохраняются ни в одном поле.
        for record in records:
            values = ' '.join(str(value) for value in vars(record).values())
            self.assertNotIn('pass', values.replace('/login/', ''))


class RequestLogTests(TestCase):
    def setUp(self):
        self.editor = make_editor()
        self.client.force_login(self.editor)
        ActivityLog.objects.all().delete()

    def test_page_view_is_logged(self):
        teacher = make_teacher()
        self.assertEqual(self.client.get(teacher.get_absolute_url()).status_code, 200)
        record = ActivityLog.objects.get()
        self.assertEqual((record.action, record.user, record.path), (A.VIEW, self.editor, teacher.get_absolute_url()))
        self.assertEqual(record.url_name, 'staff:teacher_detail')

    def test_skipped_requests(self):
        superuser = User.objects.create_superuser('root', password='secret')
        self.client.force_login(superuser)
        ActivityLog.objects.all().delete()
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertEqual(self.client.get('/teachers/999/').status_code, 404)
        self.client.logout()
        ActivityLog.objects.all().delete()  # выход сам по себе пишется
        self.client.get('/')  # анонимный — перенаправление на вход
        self.assertEqual(actions(), [])
        teacher = make_teacher()
        self.client.force_login(make_teacher_user(teacher))
        ActivityLog.objects.all().delete()
        self.assertEqual(self.client.get(reverse('staff:teacher_list')).status_code, 403)
        self.assertEqual(actions(), [])

    def test_docx_download_is_export(self):
        teacher = make_teacher()
        response = self.client.get(reverse('reports:form16', args=['teacher', teacher.pk]), {'format': 'docx'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actions(), [A.EXPORT])

    def test_ip_from_proxy_header_only_when_trusted(self):
        teacher = make_teacher()
        self.client.get(teacher.get_absolute_url(), HTTP_X_REAL_IP='203.0.113.5', REMOTE_ADDR='10.0.0.2')
        with override_settings(ACTIVITY_TRUST_PROXY_HEADER=True):
            self.client.get(teacher.get_absolute_url(), HTTP_X_REAL_IP='203.0.113.5', REMOTE_ADDR='10.0.0.2')
            self.client.get(teacher.get_absolute_url(), HTTP_X_FORWARDED_FOR='198.51.100.7, 10.0.0.1')
        self.assertEqual(list(ActivityLog.objects.order_by('pk').values_list('ip', flat=True)),
                         ['10.0.0.2', '203.0.113.5', '198.51.100.7'])

    def test_logging_failure_does_not_break_request(self):
        teacher = make_teacher()
        with mock.patch.object(ActivityLog, 'save', side_effect=RuntimeError('db down')), \
                self.assertLogs('apps.activity.log', level='ERROR'):
            self.assertEqual(self.client.get(teacher.get_absolute_url()).status_code, 200)


class DataChangeLogTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.client.force_login(make_teacher_user(self.teacher))

    def data(self, title, initial=0, author_id=None):
        authors = [{'teacher': self.teacher.pk, **({'id': author_id} if author_id else {})}]
        return {'kind': 'article', 'title': title, 'year': '2026', **formset_data('authors', authors, initial)}

    def changes(self):
        return list(ActivityLog.objects.filter(action__in=[A.CREATE, A.UPDATE, A.DELETE]).order_by('pk')
                    .values_list('action', 'content_type__model', 'object_repr'))

    def test_create_update_delete_publication_one_record_each(self):
        self.client.post(reverse('publications:publication_create'), self.data('Новая статья'))
        publication = Publication.objects.get()
        author = PublicationAuthor.objects.get()
        self.client.post(reverse('publications:publication_update', args=[publication.pk]),
                         self.data('Исправленная статья', initial=1, author_id=author.pk))
        self.client.post(reverse('publications:publication_delete', args=[publication.pk]))
        self.assertEqual(self.changes(), [
            (A.CREATE, 'publication', 'Новая статья'),
            (A.UPDATE, 'publication', 'Исправленная статья'),
            (A.DELETE, 'publication', 'Исправленная статья'),
        ])

    def test_admin_changes_are_logged(self):
        conference = Conference.objects.create(title='Конференция', level='national', start_date='2026-05-01')
        self.client.force_login(User.objects.create_superuser('root', password='secret'))
        self.client.post(reverse('admin:conferences_conference_delete', args=[conference.pk]), {'post': 'yes'})
        self.assertEqual(self.changes(), [(A.DELETE, 'conference', 'Конференция')])

    def test_changes_without_request_are_not_logged(self):
        Publication.objects.create(title='Из shell', year=2026)
        self.assertEqual(self.changes(), [])


@override_settings(DEBUG=True, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CommandTests(TestCase):
    def test_purge_removes_only_old_records(self):
        now = timezone.now()
        ActivityLog.objects.create(username='old', action=A.VIEW, created_at=now - datetime.timedelta(days=40))
        ActivityLog.objects.create(username='new', action=A.VIEW, created_at=now - datetime.timedelta(days=5))
        out = StringIO()
        call_command('purge_activity_log', days=30, stdout=out)
        self.assertIn('1', out.getvalue())
        self.assertEqual(list(ActivityLog.objects.values_list('username', flat=True)), ['new'])
        with override_settings(ACTIVITY_LOG_DAYS=1):
            call_command('purge_activity_log', stdout=StringIO())
        self.assertFalse(ActivityLog.objects.exists())

    def test_seed_demo_does_not_log_through_signals_and_clear_data_clears_log(self):
        User.objects.create_superuser('admin', password='123')
        with mock.patch('apps.activity.signals.write') as write:
            call_command('seed_demo', stdout=StringIO())
        write.assert_not_called()
        week_ago = timezone.now() - datetime.timedelta(days=7)
        self.assertTrue(ActivityLog.objects.filter(created_at__gte=week_ago).exists())
        call_command('clear_data', noinput=True, stdout=StringIO())
        self.assertFalse(ActivityLog.objects.exists())
