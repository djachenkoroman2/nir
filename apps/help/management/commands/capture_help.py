"""Пересъёмка иллюстраций справки на отдельной временной демонстрационной базе."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.urls import reverse

from apps.accounts.models import User
from apps.adjuncts.models import Task
from apps.conferences.models import Conference
from apps.help.capture import Shot, WebDriver, WebDriverError
from apps.help.screenshots import SCREENSHOTS, validate_capture_specs
from apps.reports.access import form16_url
from apps.schools.models import ScientificSchool
from apps.staff.models import Teacher

OUTPUT_DIR = Path(settings.BASE_DIR) / 'static' / 'help' / 'images'
PASSWORDS = {'admin': '123', 'editor': 'demo12345', 'ivanov': 'demo12345',
             'adjunct1': 'demo12345', 'student1': 'demo12345', 'reader': 'demo12345'}
LIST_SELECTORS = ('main form', 'a[href$="/add/"]', 'main table|main .list-group|main .card')
FORM_SELECTORS = ('main form .row|main form', 'main form .card|main form', 'main form button[type="submit"]')
AUTHOR_SELECTORS = ('main form', '#author-forms', '#add-author')


def _list(key, user, url):
    return Shot(key, user, url, LIST_SELECTORS, height=1200)


def _form(key, user, url, authors=False):
    return Shot(key, user, url, AUTHOR_SELECTORS if authors else FORM_SELECTORS, height=1800 if authors else 1600)


def _role_common_specs(role, user, home_url, report_url):
    """Снимки общих по теме, но не по интерфейсу глав для конкретной роли."""
    report_selectors = (
        ('main table|main .bg-white', 'a[href*="format=docx"]', 'button[onclick*="print"]')
        if role == 'reader' else
        ('main form', 'main button[type="submit"]', 'a[href*="format=docx"]|main .btn')
    )
    return (
        Shot(f'{role}-navigation', user, home_url,
             ('.navbar', 'main .row|main .card', 'a[href^="/help/"]'), 'body', 1250),
        Shot(f'{role}-help', user, reverse('help:guide', args=[role]),
             ('main h1', 'a[href$="/pdf/"]', 'main .list-group-item:first-child'), 'main', 1400),
        Shot(f'{role}-profile', user, reverse('core:profile_edit'),
             ('main form .row|main form', 'main button[type="submit"]'), 'main', 1100),
        Shot(f'{role}-report', user, report_url, report_selectors, 'main', 1400),
    )


def make_specs():
    teacher = User.objects.select_related('teacher').get(username='ivanov').teacher
    adjunct = User.objects.select_related('adjunct').get(username='adjunct1').adjunct
    student = User.objects.select_related('student').get(username='student1').student
    editor = User.objects.get(username='editor')
    conference = Conference.objects.first()
    school = ScientificSchool.objects.first()
    task_editor = Task.objects.select_related('adjunct', 'student').first()
    task_teacher = Task.objects.filter(adjunct__supervisor=teacher).first() or Task.objects.filter(student__supervisor=teacher).first()
    task_adjunct = Task.objects.filter(adjunct=adjunct).first()
    task_student = Task.objects.filter(student=student).first()
    reader_teacher = Teacher.objects.first()
    required = [conference, school, task_editor, task_teacher, task_adjunct, task_student, reader_teacher]
    if not all(required):
        raise CommandError('Во временной демо-базе не найдены записи для снимков')

    specs = [
        Shot('common-login', '', reverse('login'), ('#id_username', '#id_password', 'button[type="submit"]'), 'main .card', 900),
        _list('editor-teachers', 'editor', reverse('staff:teacher_list')),
        _form('editor-teacher-form', 'editor', reverse('staff:teacher_create')),
        _list('editor-research', 'editor', reverse('research:project_list')),
        _form('editor-research-form', 'editor', reverse('research:project_create')),
        _list('editor-cooperation', 'editor', reverse('cooperation:contract_list')),
        _form('editor-cooperation-form', 'editor', reverse('cooperation:contract_create')),
        _list('editor-publications', 'editor', reverse('publications:publication_list')),
        _form('editor-publication-form', 'editor', reverse('publications:publication_create'), True),
        _list('editor-ip', 'editor', reverse('ip:ip_list')),
        _form('editor-ip-form', 'editor', reverse('ip:ip_create'), True),
        _list('editor-conferences', 'editor', reverse('conferences:conference_list')),
        _form('editor-conference-form', 'editor', reverse('conferences:conference_create')),
        _form('editor-report-form', 'editor', reverse('conferences:report_create', args=[conference.pk]), True),
        Shot('editor-schools', 'editor', reverse('schools:school_list'),
             ('main .d-flex', 'main table', 'a[href$="/add/"]'), height=1400),
        _form('editor-school-form', 'editor', reverse('schools:school_create')),
        _list('editor-students', 'editor', reverse('students:student_list')),
        _form('editor-student-form', 'editor', reverse('students:student_create')),
        _form('editor-student-achievement-form', 'editor', reverse('students:achievement_create', args=[student.pk])),
        _list('editor-adjuncts', 'editor', reverse('adjuncts:adjunct_list')),
        _form('editor-adjunct-form', 'editor', reverse('adjuncts:adjunct_create')),
        _form('editor-plan-form', 'editor', reverse('adjuncts:stage_create', args=[adjunct.pk])),
        _form('editor-adjunct-achievement-form', 'editor', reverse('adjuncts:achievement_create', args=[adjunct.pk])),
        Shot('editor-tasks', 'editor', reverse('tasks:my_tasks'), ('main form', 'main table', 'main table a'), height=1300),
        _form('editor-task-form', 'editor', reverse('adjuncts:task_create', args=[adjunct.pk])),
        Shot('editor-task-detail', 'editor', task_editor.get_absolute_url(),
             ('form[action$="/status/"]|main .btn-group', 'main .card', 'textarea'), height=1400),
        Shot('editor-department-report', 'editor', reverse('reports:department'),
             ('main form', 'main form .card|main form', 'a[href*="format=docx"]|button[type="submit"]'), height=1500),
        Shot('admin-users', 'admin', reverse('admin:accounts_user_changelist'),
             ('#changelist-search', '#content-main .object-tools', '#result_list'), 'main', 1300),
        Shot('admin-user-form', 'admin', reverse('admin:accounts_user_change', args=[editor.pk]),
             ('main form .field-is_staff', 'main form .field-groups', 'main form .field-user_permissions'), '.field-is_staff', 1700),
        Shot('admin-teacher-link', 'admin', reverse('admin:staff_teacher_change', args=[teacher.pk]),
             ('main form .field-last_name|main form', 'main form .field-user', 'main form .submit-row'), 'main', 1500),
        Shot('admin-activity', 'admin', reverse('reports:activity'),
             ('main form', 'main form input[type="checkbox"]|main form', 'main table'), height=1400),
        Shot('teacher-cabinet', 'ivanov', teacher.get_absolute_url(),
             ('a[href="/publications/add/"]', 'main .card', 'a[href$="#supervision"]'), 'main', 1400),
        _form('teacher-publication-form', 'ivanov', reverse('publications:publication_create'), True),
        _form('teacher-ip-form', 'ivanov', reverse('ip:ip_create'), True),
        Shot('teacher-report-choice', 'ivanov', reverse('conferences:report_choose'),
             ('main form select', 'a[href*="conference"]|main a.btn', 'button[type="submit"]'), height=1100),
        Shot('teacher-student', 'ivanov', student.get_absolute_url(),
             ('a[href*="/achievements/add/"]', 'main .card', 'button[data-bs-toggle="dropdown"]|main .dropdown'), 'main', 1400),
        Shot('teacher-adjunct', 'ivanov', adjunct.get_absolute_url(),
             ('a[href*="/plan/add/"]', '#plan', 'main h3.text-muted'), '#plan', 1500),
        Shot('teacher-task', 'ivanov', task_teacher.get_absolute_url(),
             ('form[action$="/status/"]|main .btn-group', 'main .card', 'textarea'), height=1400),
        Shot('teacher-reports', 'ivanov', reverse('reports:report_list'),
             ('main .card', 'a[href*="/reports/supervision"]', 'main h1'), height=1300),
        Shot('adjunct-cabinet', 'adjunct1', adjunct.get_absolute_url(),
             ('a[href="/publications/add/"]', 'main .card', '.nav-pills'), 'main', 1400),
        _form('adjunct-publication-form', 'adjunct1', reverse('publications:publication_create'), True),
        _form('adjunct-ip-form', 'adjunct1', reverse('ip:ip_create'), True),
        Shot('adjunct-report-choice', 'adjunct1', reverse('conferences:report_choose'),
             ('main form select', 'a[href*="conference"]|main a.btn', 'button[type="submit"]'), height=1100),
        _form('adjunct-achievement-form', 'adjunct1', reverse('adjuncts:achievement_create', args=[adjunct.pk])),
        Shot('adjunct-plan', 'adjunct1', adjunct.get_absolute_url(),
             ('.list-group-item:has(form[action$="/start/"]) .badge', 'form[action$="/start/"]',
              '.list-group-item:has(form[action$="/start/"]) .text-muted'),
             '.list-group-item:has(form[action$="/start/"])', 1100),
        Shot('adjunct-task', 'adjunct1', task_adjunct.get_absolute_url(),
             ('form[action$="/status/"]|main .btn-group', 'main .card', 'textarea'), height=1400),
        Shot('adjunct-reports', 'adjunct1', reverse('reports:report_list'),
             ('a[href*="/reports/form16"]|main .card', 'a[href*="/reports/plan"]|main .card', 'main h1'), height=1300),
        Shot('student-cabinet', 'student1', student.get_absolute_url(),
             ('a[href="/publications/add/"]', 'main .card', 'a[href="/tasks/"]'), 'main', 1400),
        _form('student-publication-form', 'student1', reverse('publications:publication_create'), True),
        Shot('student-report-choice', 'student1', reverse('conferences:report_choose'),
             ('main form select', 'a[href*="conference"]|main a.btn', 'button[type="submit"]'), height=1100),
        _form('student-achievement-form', 'student1', reverse('students:achievement_create', args=[student.pk])),
        Shot('student-task', 'student1', task_student.get_absolute_url(),
             ('form[action$="/status/"]|main .btn-group', 'main .card', 'textarea'), height=1400),
        Shot('student-reports', 'student1', reverse('reports:report_list'),
             ('a[href*="/reports/form16"]|main .card', 'a[href*="/reports/card"]|main .card', 'main h1'), height=1300),
        Shot('reader-list', 'reader', reverse('staff:teacher_list'),
             ('main form', 'main table', 'main table a'), height=1200),
        Shot('reader-detail', 'reader', reader_teacher.get_absolute_url(),
             ('main dl', 'main .card', 'main h1'), height=1300),
        Shot('reader-reports', 'reader', reverse('reports:report_list'),
             ('main .card|main', 'a[href="/reports/account/"]|main', 'main h1'), height=1100),
    ]
    common_homes = {
        'admin': reverse('core:home'),
        'editor': reverse('core:home'),
        'teacher': teacher.get_absolute_url(),
        'adjunct': adjunct.get_absolute_url(),
        'student': student.get_absolute_url(),
        'reader': reverse('core:home'),
    }
    common_reports = {
        'admin': reverse('reports:department'),
        'editor': reverse('reports:department'),
        'teacher': reverse('reports:form16_own'),
        'adjunct': reverse('reports:form16_own'),
        'student': reverse('reports:form16_own'),
        'reader': reverse('reports:account'),
    }
    for role, user in (('admin', 'admin'), ('editor', 'editor'), ('teacher', 'ivanov'),
                       ('adjunct', 'adjunct1'), ('student', 'student1'), ('reader', 'reader')):
        specs.extend(_role_common_specs(role, user, common_homes[role], common_reports[role]))
    for role, user in (('admin', 'admin'), ('editor', 'editor')):
        specs.extend((
            Shot(f'{role}-person-report', user, form16_url(teacher),
                 ('main form', 'main button[type="submit"]', 'a[href*="format=docx"]|main .btn'), 'main', 1400),
            Shot(f'{role}-account', user, reverse('reports:account'),
                 ('main table|main .bg-white', 'a[href*="format=docx"]', 'button[onclick*="print"]'), 'main', 1200),
        ))
    return specs


class Command(BaseCommand):
    help = 'Снимает реальные аннотированные скриншоты на временной SQLite БД; рабочая БД не используется.'

    def add_arguments(self, parser):
        parser.add_argument('--work-dir', default='/tmp/opencode/nir-help-capture')
        parser.add_argument('--port', type=int, default=8765)
        parser.add_argument('--driver-port', type=int, default=4444)
        parser.add_argument('--seed', type=int, default=2026)
        parser.add_argument('--only', help='Ключи снимков через запятую')

    def _prepare_database(self, db_path, seed):
        if db_path.exists():
            db_path.unlink()
        connections['default'].close()
        connections.databases['default']['NAME'] = str(db_path)
        call_command('migrate', interactive=False, verbosity=0)
        call_command('create_admin', verbosity=0)
        call_command('seed_demo', seed=seed, force=True, verbosity=0)
        User.objects.create_user('reader', password='demo12345', first_name='Читатель', last_name='Демонстрационный',
                                 email='reader@example.edu')

    @staticmethod
    def _wait_url(url, timeout=60):
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status < 500:
                        return
            except Exception as exc:  # процесс ещё запускается
                last_error = exc
            time.sleep(.15)
        raise CommandError(f'Сервис не запустился: {url}: {last_error}')

    def handle(self, *args, **options):
        work_dir = Path(options['work_dir']).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        db_path = work_dir / 'capture.sqlite3'
        self.stdout.write(f'Временная база: {db_path}')
        self._prepare_database(db_path, options['seed'])
        specs = make_specs()
        spec_errors = validate_capture_specs(specs)
        if spec_errors:
            raise CommandError('Карта снимков не совпадает с реестром:\n' + '\n'.join(spec_errors))
        by_key = {shot.key: shot for shot in specs}
        if options['only']:
            selected = [key.strip() for key in options['only'].split(',') if key.strip()]
            unknown = set(selected) - set(by_key)
            if unknown:
                raise CommandError(f'Неизвестные ключи: {sorted(unknown)}')
            specs = [by_key[key] for key in selected]

        server = driver_process = None
        server_log = (work_dir / 'runserver.log').open('w')
        driver_log = (work_dir / 'geckodriver.log').open('w')
        base_url = f'http://127.0.0.1:{options["port"]}'
        endpoint = f'http://127.0.0.1:{options["driver_port"]}'
        env = os.environ.copy()
        # config.settings намеренно читает .env с override=True, поэтому одного DB_NAME в env недостаточно.
        # Временный модуль применяет путь уже после импорта основных настроек и не меняет пользовательский .env.
        (work_dir / 'capture_settings.py').write_text(
            'from config.settings import *\n'
            f'DATABASES["default"]["NAME"] = {str(db_path)!r}\n'
            'DEBUG = True\n',
            encoding='utf-8',
        )
        env.update(
            DB_NAME=str(db_path), DJANGO_DEBUG='True', DJANGO_SECRET_KEY='help-capture-temporary-secret',
            DJANGO_SETTINGS_MODULE='capture_settings',
            PYTHONPATH=str(work_dir) + os.pathsep + env.get('PYTHONPATH', str(settings.BASE_DIR)),
        )
        try:
            server = subprocess.Popen(
                [sys.executable, str(Path(settings.BASE_DIR) / 'manage.py'), 'runserver',
                 f'127.0.0.1:{options["port"]}', '--noreload'],
                cwd=settings.BASE_DIR, env=env, stdout=server_log, stderr=subprocess.STDOUT,
            )
            self._wait_url(base_url + reverse('login'))
            geckodriver = shutil.which('geckodriver')
            if not geckodriver:
                raise CommandError('Для пересъёмки нужен geckodriver в PATH')
            driver_process = subprocess.Popen(
                [geckodriver, '--host', '127.0.0.1', '--port', str(options['driver_port'])],
                stdout=driver_log, stderr=subprocess.STDOUT,
            )
            self._wait_url(endpoint + '/status')
            current_user = object()
            browser = None
            completed = []
            try:
                for shot in specs:
                    if shot.user != current_user:
                        if browser is not None:
                            browser.close()
                        browser = WebDriver(endpoint, base_url)
                        browser.start()
                        current_user = shot.user
                        if shot.user:
                            browser.login(shot.user, PASSWORDS[shot.user])
                    self.stdout.write(f'{shot.key}: {shot.url}')
                    browser.capture(shot, OUTPUT_DIR / SCREENSHOTS[shot.key].filename)
                    completed.append(shot.key)
            finally:
                if browser is not None:
                    browser.close()
            self.stdout.write(self.style.SUCCESS(f'Создано скриншотов: {len(completed)} в {OUTPUT_DIR}'))
        except (WebDriverError, OSError, subprocess.SubprocessError) as exc:
            raise CommandError(f'Ошибка пересъёмки: {exc}\nЛоги: {server_log.name}, {driver_log.name}') from exc
        finally:
            for process in (driver_process, server):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
            server_log.close()
            driver_log.close()
