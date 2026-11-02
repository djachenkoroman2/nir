"""Резервное копирование: база данных + .env.

Копия базы SQLite создаётся через Online Backup API (консистентно даже при работающем
сервере), PostgreSQL — через pg_dump. Копия .env сохраняется с правами 600.
"""
import datetime
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

ENV_FILE = settings.BASE_DIR / '.env'
DEFAULT_DIR = settings.BASE_DIR / 'backups'

# Имена копий: db-ГГГГ-ММ-ДД.sqlite3, nir-ГГГГ-ММ-ДД.dump, env-ГГГГ-ММ-ДД.
COPY_NAME_RE = re.compile(
    r'^(?:db-\d{4}-\d{2}-\d{2}\.sqlite3|nir-\d{4}-\d{2}-\d{2}\.dump|env-\d{4}-\d{2}-\d{2})$'
)
DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def copy_date(name):
    """Дата из имени копии или None, если файл не похож на копию."""
    match = COPY_NAME_RE.match(name)
    if not match:
        return None
    try:
        return datetime.date(*(int(part) for part in DATE_RE.search(name).groups()))
    except ValueError:
        return None


def rotate_backups(directory, keep_days, today):
    """Удаляет копии старше keep_days по дате в имени. Возвращает число удалённых файлов."""
    border = today - datetime.timedelta(days=keep_days)
    removed = 0
    for path in Path(directory).iterdir():
        if not path.is_file():
            continue
        date = copy_date(path.name)
        if date is not None and date < border:
            path.unlink()
            removed += 1
    return removed


def temporary_copy_path(target):
    """Временный файл рядом с итоговым: os.replace затем заменит копию атомарно."""
    target = Path(target)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=f'.{target.name}.', suffix='.tmp')
    os.close(descriptor)
    return Path(name)


def create_sqlite_backup(source, target):
    """Копия SQLite через Online Backup API: читает исходный файл, не мешая работе сервера."""
    if not Path(source).is_file():
        raise CommandError(f'Файл базы данных не найден: {source}')
    source_conn = sqlite3.connect(str(source))
    try:
        target_conn = sqlite3.connect(str(target))
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()


def check_sqlite_backup(path):
    """PRAGMA integrity_check по созданной копии: список сообщений об ошибках (пусто — копия целостна)."""
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute('PRAGMA integrity_check').fetchall()
        if not rows:
            return ['PRAGMA integrity_check вернул пустой результат']
        return [row[0] for row in rows if row[0] != 'ok']
    finally:
        conn.close()


def create_postgresql_backup(db, target):
    """Копия PostgreSQL через pg_dump (формат custom)."""
    env = {**os.environ, 'PGPASSWORD': db.get('PASSWORD', '')}
    command = [
        'pg_dump', '--format=custom', f'--file={target}',
        f'--dbname={db["NAME"]}', f'--host={db.get("HOST") or "localhost"}',
        f'--port={str(db.get("PORT") or "5432")}', f'--username={db.get("USER") or ""}',
    ]
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True)
    except FileNotFoundError:
        raise CommandError('pg_dump не найден. Установите PostgreSQL-клиент: sudo apt install -y postgresql-client')
    if result.returncode != 0:
        raise CommandError(f'pg_dump завершился с ошибкой: {result.stderr.strip()}')


def copy_env_file(source, target):
    """Копия .env с правами 600: в ней секретный ключ и пароли."""
    target = Path(target)
    temporary = temporary_copy_path(target)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def human_size(size):
    if size >= 1024 * 1024:
        return f'{size / 1024 / 1024:.1f} МБ'
    if size >= 1024:
        return f'{size / 1024:.1f} КБ'
    return f'{size} байт'


class Command(BaseCommand):
    help = 'Создаёт резервную копию базы данных и .env, удаляет копии старше срока хранения.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=str(DEFAULT_DIR),
                            help='Каталог для копий (по умолчанию — backups/ в корне проекта).')
        parser.add_argument('--keep', type=int, default=30,
                            help='Сколько дней хранить копии (по умолчанию 30). Копии старше удаляются.')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        today = timezone.localdate()
        stamp = today.isoformat()
        if options['keep'] < 0:
            raise CommandError('Параметр --keep должен быть неотрицательным числом дней.')
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        if db['ENGINE'] == 'django.db.backends.sqlite3':
            db_copy = output_dir / f'db-{stamp}.sqlite3'
        elif db['ENGINE'] == 'django.db.backends.postgresql':
            db_copy = output_dir / f'nir-{stamp}.dump'
        else:
            raise CommandError(f'Неизвестный движок базы данных: {db["ENGINE"]}')

        temporary = temporary_copy_path(db_copy)
        try:
            if db['ENGINE'] == 'django.db.backends.sqlite3':
                create_sqlite_backup(db['NAME'], temporary)
                errors = check_sqlite_backup(temporary)
                if errors:
                    raise CommandError(f'Копия базы повреждена (integrity_check: {"; ".join(errors)}), файл удалён.')
            else:
                create_postgresql_backup(db, temporary)
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(temporary, db_copy)
        finally:
            temporary.unlink(missing_ok=True)

        self.stdout.write(f'Копия базы данных: {db_copy} ({human_size(db_copy.stat().st_size)})')

        if not ENV_FILE.is_file():
            raise CommandError(f'Файл {ENV_FILE} не найден — копия настроек не создана.')
        env_copy = output_dir / f'env-{stamp}'
        copy_env_file(ENV_FILE, env_copy)
        self.stdout.write(f'Копия настроек: {env_copy} ({human_size(env_copy.stat().st_size)})')

        removed = rotate_backups(output_dir, options['keep'], today)
        self.stdout.write(f'Удалено копий старше {options["keep"]} дн.: {removed}')
        self.stdout.write(self.style.SUCCESS(f'Резервное копирование завершено: {output_dir}'))
