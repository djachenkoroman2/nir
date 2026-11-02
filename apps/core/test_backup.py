import os
import sqlite3
import stat
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from apps.core.management.commands import backup


def run_backup(**options):
    out = StringIO()
    call_command('backup', stdout=out, stderr=out, **options)
    return out.getvalue()


class BackupCommandTests(SimpleTestCase):
    """Команда работает с отдельной временной файловой БД, а не с SQLite in memory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output_dir = Path(self.tmp.name) / 'backups'
        self.output_dir.mkdir()
        self.source = Path(self.tmp.name) / 'custom-name.sqlite3'
        conn = sqlite3.connect(self.source)
        try:
            conn.execute('CREATE TABLE entries (value TEXT)')
            conn.execute("INSERT INTO entries VALUES ('актуальные данные')")
            conn.commit()
        finally:
            conn.close()

        databases = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': self.source}}
        settings_patch = mock.patch.object(backup.settings, 'DATABASES', databases)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

        self.env = Path(self.tmp.name) / 'fake.env'
        self.env.write_text('DJANGO_SECRET_KEY=top-secret')
        env_patch = mock.patch.object(backup, 'ENV_FILE', self.env)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def db_copy(self):
        return self.output_dir / f'db-{backup.timezone.localdate().isoformat()}.sqlite3'

    def copied_values(self):
        conn = sqlite3.connect(self.db_copy())
        try:
            return [row[0] for row in conn.execute('SELECT value FROM entries')]
        finally:
            conn.close()

    def test_creates_consistent_copy_from_db_name_with_actual_data(self):
        output = run_backup(output_dir=str(self.output_dir))
        self.assertTrue(self.db_copy().is_file())
        self.assertEqual(self.copied_values(), ['актуальные данные'])
        self.assertEqual(stat.S_IMODE(self.db_copy().stat().st_mode), stat.S_IRUSR | stat.S_IWUSR)
        self.assertIn('Копия базы данных', output)
        self.assertIn('Удалено копий старше 30 дн.: 0', output)
        self.assertIn('Резервное копирование завершено', output)

    def test_rerun_same_day_overwrites(self):
        run_backup(output_dir=str(self.output_dir))
        conn = sqlite3.connect(self.source)
        try:
            conn.execute("INSERT INTO entries VALUES ('новая запись')")
            conn.commit()
        finally:
            conn.close()
        run_backup(output_dir=str(self.output_dir))  # не падает, если копия за сегодня уже есть
        self.assertEqual(len(list(self.output_dir.glob('db-*.sqlite3'))), 1)
        self.assertEqual(self.copied_values(), ['актуальные данные', 'новая запись'])

    def test_failed_integrity_check_removes_copy(self):
        with mock.patch('apps.core.management.commands.backup.check_sqlite_backup',
                        return_value=['database disk image is malformed']), \
             self.assertRaisesMessage(CommandError, 'повреждена'):
            run_backup(output_dir=str(self.output_dir))
        self.assertFalse(self.db_copy().exists())

    def test_integrity_check_error_removes_copy(self):
        with mock.patch('apps.core.management.commands.backup.check_sqlite_backup',
                        side_effect=sqlite3.DatabaseError('check failed')), \
             self.assertRaises(sqlite3.DatabaseError):
            run_backup(output_dir=str(self.output_dir))
        self.assertFalse(self.db_copy().exists())
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_failed_rerun_preserves_previous_copy(self):
        run_backup(output_dir=str(self.output_dir))
        with mock.patch('apps.core.management.commands.backup.check_sqlite_backup',
                        return_value=['database disk image is malformed']), \
             self.assertRaisesMessage(CommandError, 'повреждена'):
            run_backup(output_dir=str(self.output_dir))
        self.assertEqual(self.copied_values(), ['актуальные данные'])
        self.assertEqual(list(self.output_dir.glob('.*.tmp')), [])

    def test_env_copy_created_with_600_permissions(self):
        target = self.output_dir / f'env-{backup.timezone.localdate().isoformat()}'
        run_backup(output_dir=str(self.output_dir))
        self.assertEqual(target.read_text(), 'DJANGO_SECRET_KEY=top-secret')
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), stat.S_IRUSR | stat.S_IWUSR)

    def test_missing_env_fails(self):
        self.env.unlink()
        with self.assertRaisesMessage(CommandError, 'не найден'):
            run_backup(output_dir=str(self.output_dir))
        self.assertTrue(self.db_copy().is_file())
        self.assertEqual(list(self.output_dir.glob('env-*')), [])

    def test_rotation_removes_only_expired_copies(self):
        today = backup.timezone.localdate()
        old = today - backup.datetime.timedelta(days=40)
        fresh = today - backup.datetime.timedelta(days=10)
        for name in (f'db-{old}.sqlite3', f'nir-{old}.dump', f'env-{old}',
                     f'db-{fresh}.sqlite3', f'env-{fresh}'):
            (self.output_dir / name).touch()
        (self.output_dir / 'заметки.txt').touch()
        output = run_backup(output_dir=str(self.output_dir), keep=30)
        self.assertIn('Удалено копий старше 30 дн.: 3', output)
        for name in (f'db-{old}.sqlite3', f'nir-{old}.dump', f'env-{old}'):
            self.assertFalse((self.output_dir / name).exists(), name)
        for name in (f'db-{fresh}.sqlite3', f'env-{fresh}', 'заметки.txt'):
            self.assertTrue((self.output_dir / name).exists(), name)
        self.assertTrue(self.db_copy().is_file())

    def test_negative_keep_fails_before_creating_copy(self):
        with self.assertRaisesMessage(CommandError, '--keep должен быть неотрицательным'):
            run_backup(output_dir=str(self.output_dir), keep=-1)
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_unknown_engine_fails(self):
        databases = {'default': {'ENGINE': 'django.db.backends.mysql', 'NAME': 'x'}}
        with mock.patch.object(backup.settings, 'DATABASES', databases):
            with self.assertRaisesMessage(CommandError, 'Неизвестный движок'):
                run_backup(output_dir=str(self.output_dir))
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_copy_date_parses_only_backup_names(self):
        today = backup.timezone.localdate()
        self.assertEqual(backup.copy_date(f'db-{today}.sqlite3'), today)
        self.assertEqual(backup.copy_date(f'nir-{today}.dump'), today)
        self.assertEqual(backup.copy_date(f'env-{today}'), today)
        for name in ('db.sqlite3', f'db-{today}.bak', f'db-{today}.dump', f'nir-{today}.sqlite3',
                     'env-copy', 'заметки.txt', 'db-2026-02-30.sqlite3'):
            self.assertIsNone(backup.copy_date(name), name)


class BackupPostgresqlTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output_dir = Path(self.tmp.name) / 'backups'
        self.output_dir.mkdir()
        databases = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': 'nir', 'USER': 'nir', 'PASSWORD': 'secret',
                'HOST': 'localhost', 'PORT': '5432',
            }
        }
        settings_patch = mock.patch.object(backup.settings, 'DATABASES', databases)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        env = Path(self.tmp.name) / 'fake.env'
        env.write_text('DJANGO_SECRET_KEY=top-secret')
        env_patch = mock.patch.object(backup, 'ENV_FILE', env)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_uses_pg_dump_with_settings_password(self):
        result = mock.Mock(returncode=0, stderr='')

        def create_dump(command, **kwargs):
            target = next(arg.split('=', 1)[1] for arg in command if arg.startswith('--file='))
            Path(target).write_bytes(b'postgresql dump')
            return result

        with mock.patch('apps.core.management.commands.backup.subprocess.run', side_effect=create_dump) as run:
            output = run_backup(output_dir=str(self.output_dir))
        command = run.call_args.args[0]
        self.assertEqual(command[0], 'pg_dump')
        self.assertIn('--format=custom', command)
        self.assertIn('--dbname=nir', command)
        self.assertIn('--username=nir', command)
        self.assertIn('--host=localhost', command)
        self.assertIn('--port=5432', command)
        self.assertEqual(run.call_args.kwargs['env']['PGPASSWORD'], 'secret')
        target = self.output_dir / f'nir-{backup.timezone.localdate().isoformat()}.dump'
        file_argument = next(arg for arg in command if arg.startswith('--file='))
        temporary = Path(file_argument.split('=', 1)[1])
        self.assertEqual(temporary.parent, self.output_dir)
        self.assertTrue(temporary.name.startswith(f'.{target.name}.'))
        self.assertFalse(temporary.exists())
        self.assertEqual(target.read_bytes(), b'postgresql dump')
        self.assertIn('Резервное копирование завершено', output)

    def test_pg_dump_failure_removes_partial_dump_and_preserves_previous_copy(self):
        target = self.output_dir / f'nir-{backup.timezone.localdate().isoformat()}.dump'
        target.write_bytes(b'previous good dump')
        result = mock.Mock(returncode=1, stderr='connection refused')

        def fail_with_partial_dump(command, **kwargs):
            temporary = next(arg.split('=', 1)[1] for arg in command if arg.startswith('--file='))
            Path(temporary).write_bytes(b'partial dump')
            return result

        with mock.patch('apps.core.management.commands.backup.subprocess.run',
                        side_effect=fail_with_partial_dump), \
             self.assertRaisesMessage(CommandError, 'pg_dump завершился с ошибкой'):
            run_backup(output_dir=str(self.output_dir))
        self.assertEqual(target.read_bytes(), b'previous good dump')
        self.assertEqual(list(self.output_dir.glob('.*.tmp')), [])

    def test_pg_dump_missing_raises(self):
        with mock.patch('apps.core.management.commands.backup.subprocess.run',
                        side_effect=FileNotFoundError), \
             self.assertRaisesMessage(CommandError, 'pg_dump не найден'):
            run_backup(output_dir=str(self.output_dir))
