from io import StringIO
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.core.management.commands._base import DOMAIN_MODELS
from apps.core.management.commands.seed_demo import DEMO_PASSWORD
from apps.publications.models import Publication
from apps.schools.indicators import indicator_totals
from apps.schools.models import ScientificSchool
from apps.schools.period import report_period
from apps.staff.models import Teacher


# Быстрый хешер: seed_demo создаёт несколько пользователей, стандартный PBKDF2 сильно замедляет тесты.
FAST_HASHER = ['django.contrib.auth.hashers.MD5PasswordHasher']


def run(*args, **kwargs):
    out = StringIO()
    call_command(*args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


@override_settings(DEBUG=True, PASSWORD_HASHERS=FAST_HASHER)
class SeedDemoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='123')

    def test_creates_records_of_every_model_and_demo_users(self):
        output = run('seed_demo')
        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                self.assertTrue(model.objects.exists())
        self.assertIn('Демонстрационные данные созданы', output)

        editor = User.objects.get(username='editor')
        self.assertTrue(editor.is_staff)
        self.assertTrue(editor.check_password(DEMO_PASSWORD))
        self.assertTrue(editor.groups.filter(name='Редакторы НИР').exists())
        for login in ('ivanov', 'petrova', 'smirnov'):
            with self.subTest(login=login):
                user = User.objects.get(username=login)
                self.assertFalse(user.is_staff)
                self.assertTrue(user.groups.filter(name='Преподаватели').exists())
                self.assertTrue(user.teacher.publicationauthor_set.exists())

    def test_covers_all_choices(self):
        run('seed_demo')
        self.assertEqual(set(Publication.objects.values_list('kind', flat=True)), set(Publication.Kind.values))
        self.assertTrue(Teacher.objects.filter(is_active=False).exists())
        self.assertTrue(ScientificSchool.objects.filter(is_active=False).exists())

    def test_school_indicators_are_not_empty(self):
        run('seed_demo')
        totals = indicator_totals(ScientificSchool.objects.filter(is_active=True), report_period())
        for key, value in totals.items():
            with self.subTest(indicator=key):
                self.assertGreater(value, 0)
        first_year = report_period()[0]
        self.assertTrue(Publication.objects.filter(year__lt=first_year).exists(), 'нужны записи до периода')

    def test_does_not_duplicate_without_clear(self):
        run('seed_demo')
        count = Publication.objects.count()
        output = run('seed_demo')
        self.assertIn('В базе уже есть данные', output)
        self.assertEqual(Publication.objects.count(), count)

    def test_same_seed_gives_same_data(self):
        def snapshot():
            return list(Publication.objects.order_by('title').values_list('title', 'year', 'kind', 'vak'))

        run('seed_demo', seed=7)
        first = snapshot()
        run('seed_demo', seed=7, clear=True)
        self.assertEqual(snapshot(), first)
        run('seed_demo', seed=8, clear=True)
        self.assertNotEqual(snapshot(), first)

    def test_clear_option_keeps_admin(self):
        run('seed_demo')
        run('seed_demo', clear=True)
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertEqual(Teacher.objects.count(), 14)


@override_settings(DEBUG=True, PASSWORD_HASHERS=FAST_HASHER)
class ClearDataTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', password='123')
        run('seed_demo')

    def test_deletes_everything_except_admin_groups_and_permissions(self):
        permissions_before = {group.name: group.permissions.count() for group in Group.objects.all()}
        output = run('clear_data', noinput=True)
        self.assertIn('База очищена', output)
        for model in DOMAIN_MODELS:
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.exists())
        self.assertEqual(list(User.objects.values_list('username', flat=True)), ['admin'])
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)
        self.assertTrue(self.admin.check_password('123'))
        self.assertEqual({group.name: group.permissions.count() for group in Group.objects.all()}, permissions_before)

    def test_does_nothing_without_kept_user(self):
        output = run('clear_data', username='nobody', noinput=True)
        self.assertIn('не найден', output)
        self.assertTrue(Publication.objects.exists())
        self.assertEqual(User.objects.count(), 5)

    def test_asks_for_confirmation(self):

        with mock.patch('builtins.input', return_value='no'):
            output = run('clear_data')
        self.assertIn('Отменено', output)
        self.assertTrue(Publication.objects.exists())
        with mock.patch('builtins.input', return_value='yes'):
            run('clear_data')
        self.assertFalse(Publication.objects.exists())


@override_settings(DEBUG=False, PASSWORD_HASHERS=FAST_HASHER)
class ProductionGuardTests(TestCase):
    def test_commands_refuse_without_force(self):
        User.objects.create_superuser('admin', password='123')
        for command in ('seed_demo', 'clear_data'):
            with self.subTest(command=command), self.assertRaisesMessage(CommandError, '--force'):
                call_command(command, stdout=StringIO())
        self.assertFalse(Teacher.objects.exists())
        run('seed_demo', force=True)
        self.assertTrue(Teacher.objects.exists())
        run('clear_data', force=True, noinput=True)
        self.assertFalse(Teacher.objects.exists())
