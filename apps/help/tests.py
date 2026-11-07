from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .content import COMMON_CHAPTER_SLUGS, GUIDES, ROLE_COMMON, chapters_for, get_chapter, validate_content
from .coverage import coverage_rows
from .guide_editor import DOMAINS
from .language import NON_ADMIN_ROLES, TECHNICAL_PATTERNS, technical_terms
from .pdf import GENERATED_DIR, inspect_pdf, pdf_text
from .roles import accessible_guides, can_view_role, role_for_user
from .screenshots import (
    ROLE_DEMO_USERS, SCREENSHOTS, validate_capture_specs, validate_screenshot_registry,
)


def guide_text(role):
    """Все авторские поля руководства для точных регрессионных проверок."""
    values = []
    for item in chapters_for(role):
        values.extend((item.title, item.intro))
        for scenario in item.scenarios:
            values.extend((
                scenario.title, scenario.goal, scenario.preconditions, *scenario.steps,
                scenario.example, scenario.result, *scenario.errors, scenario.related,
            ))
            shot = scenario.image
            values.extend((shot.title, shot.alt, *shot.legend))
    return '\n'.join(values)


def scenario(role, chapter_slug, scenario_slug):
    item = get_chapter(role, chapter_slug)
    return next(value for value in item.scenarios if value.slug == scenario_slug)


class HelpFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('admin', password='secret')
        cls.editor = make_editor()
        teacher = make_teacher()
        cls.teacher = make_teacher_user(teacher)
        adjunct = make_adjunct(teacher)
        cls.adjunct = make_adjunct_user(adjunct)
        student = make_student(supervisor=teacher)
        cls.student = make_student_user(student)
        cls.reader = User.objects.create_user('reader', password='secret')
        cls.users = {
            'admin': cls.admin, 'editor': cls.editor, 'teacher': cls.teacher,
            'adjunct': cls.adjunct, 'student': cls.student, 'reader': cls.reader,
        }


class RoleTests(HelpFixture):
    def test_role_for_user_matches_effective_access(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.assertEqual(role_for_user(user), role)

    def test_editor_with_person_card_remains_editor(self):
        teacher = make_teacher(last_name='Совмещённый')
        teacher.user = self.editor
        teacher.save()
        self.assertEqual(role_for_user(self.editor), 'editor')

    def test_group_without_card_is_reader(self):
        user = User.objects.create_user('group_without_card')
        from django.contrib.auth.models import Group
        user.groups.add(Group.objects.get(name='Преподаватели'))
        self.assertEqual(role_for_user(user), 'reader')

    def test_access_policy(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.assertTrue(can_view_role(user, role))
                self.assertEqual(can_view_role(user, 'unknown'), False)
                if role not in ('admin', 'editor'):
                    other = 'adjunct' if role != 'adjunct' else 'student'
                    self.assertFalse(can_view_role(user, other))
        for user in (self.admin, self.editor):
            self.assertEqual({guide.slug for guide in accessible_guides(user)}, set(GUIDES))


class ContentTests(TestCase):
    def test_content_is_complete(self):
        self.assertEqual(validate_content(), [])
        self.assertEqual(set(GUIDES), {'admin', 'editor', 'teacher', 'adjunct', 'student', 'reader'})
        required = {
            'admin': {'administration', 'reports', 'tasks'},
            'editor': {'teachers', 'research', 'cooperation', 'publications', 'ip', 'conferences', 'schools',
                       'students', 'adjuncts', 'reports', 'tasks'},
            'teacher': {'teacher-cabinet', 'teacher-publications', 'teacher-ip', 'teacher-students',
                        'teacher-adjuncts', 'teacher-tasks', 'teacher-reporting'},
            'adjunct': {'adjunct-cabinet', 'adjunct-publications', 'adjunct-ip', 'adjunct-achievements',
                        'adjunct-plan', 'adjunct-tasks', 'adjunct-reporting'},
            'student': {'student-cabinet', 'student-publications', 'student-ip', 'student-achievements',
                        'student-tasks', 'student-reporting'},
            'reader': {'reader-teachers', 'reader-research', 'reader-cooperation', 'reader-publications',
                       'reader-ip', 'reader-conferences', 'reader-schools', 'reader-students', 'reader-adjuncts',
                       'reader-account'},
        }
        for role, chapters in required.items():
            with self.subTest(role=role):
                slugs = {item.slug for item in chapters_for(role)}
                self.assertLessEqual(chapters, slugs)
                common_slugs = tuple(item.slug for item in chapters_for(role)[:len(COMMON_CHAPTER_SLUGS)])
                self.assertEqual(COMMON_CHAPTER_SLUGS, common_slugs)

    def test_common_chapters_have_distinct_role_content(self):
        self.assertEqual(set(ROLE_COMMON), set(GUIDES))
        login_examples = set()
        report_examples = set()
        for role in GUIDES:
            with self.subTest(role=role):
                login = scenario(role, 'getting-started', 'login')
                navigation = scenario(role, 'interface', 'navigation')
                profile = scenario(role, 'account-and-documents', 'profile')
                report = scenario(role, 'account-and-documents', 'reports-and-print')
                using_help = scenario(role, 'account-and-documents', 'using-help')
                self.assertEqual(login.example, ROLE_COMMON[role]['login_example'])
                self.assertIn(f'логин {ROLE_DEMO_USERS[role]}', login.example)
                self.assertEqual(report.example, ROLE_COMMON[role]['report_example'])
                self.assertEqual(navigation.screenshot, f'{role}-navigation')
                self.assertEqual(profile.screenshot, f'{role}-profile')
                self.assertEqual(report.screenshot, f'{role}-report')
                self.assertEqual(using_help.screenshot, f'{role}-help')
                login_examples.add(login.example)
                report_examples.add(report.example)
        self.assertEqual(len(login_examples), len(GUIDES))
        self.assertEqual(len(report_examples), len(GUIDES))

    def test_known_cross_role_regressions_are_removed(self):
        removed = (
            'Для демонстрационной среды преподаватель вводит логин ivanov',
            'Руководитель выбирает «Мои подопечные»',
            'Исправьте адрес на ivanov@example.edu и проверьте, что тот же адрес отображается в связанной карточке преподавателя.',
            'руководителя или подопечного',
            'Вы вошли как редактор или администратор',
            'У вас есть права редактора; пользователь только для просмотра',
        )
        for role in GUIDES:
            text = guide_text(role)
            for phrase in removed:
                with self.subTest(role=role, phrase=phrase):
                    self.assertNotIn(phrase, text)
        reader_text = guide_text('reader')
        for domain in DOMAINS:
            with self.subTest(reader_domain=domain['slug']):
                self.assertNotIn(domain['delete'], reader_text)

    def test_non_admin_guides_use_plain_language(self):
        for role in NON_ADMIN_ROLES:
            with self.subTest(role=role):
                self.assertEqual(technical_terms(guide_text(role)), [])

    def test_technical_language_detector_and_domain_allowances(self):
        sample = (
            'POST GET HTTP 403 404 is_staff is_superuser activity.view_activity_report '
            '?then=report all=1 /add/ /edit/ /delete/ Django ORM middleware '
            'числовой ID числовой идентификатор суперпользователь прямой адрес прямые URL'
        )
        self.assertEqual(len(technical_terms(sample)), len(TECHNICAL_PATTERNS))
        allowed = 'DOI и ссылка (URL) на издание, PDF, DOCX, НИОКР, РИД, РИНЦ, ВАК, Scopus, WoS'
        self.assertEqual(technical_terms(allowed), [])

    def test_plain_language_preserves_user_actions(self):
        for role in GUIDES:
            with self.subTest(role=role, scenario='logout-and-access'):
                steps = scenario(role, 'getting-started', 'logout-and-access').steps
                self.assertEqual(steps[0], 'Для завершения работы нажмите «Выйти» в правой части шапки.')
                self.assertIn('Если раздел недоступен вашей роли', steps[1])
                self.assertIn('обратитесь к администратору', steps[1])
                self.assertIn('Если запись не найдена или недоступна', steps[2])
                self.assertIn('вернитесь к своему списку', steps[2])
        conference_chapters = {
            'admin': 'conferences', 'editor': 'conferences', 'teacher': 'teacher-conferences',
            'adjunct': 'adjunct-conferences', 'student': 'student-conferences',
        }
        for role, chapter_slug in conference_chapters.items():
            with self.subTest(role=role, scenario='report-create'):
                steps = scenario(role, chapter_slug, 'report-create').steps
                self.assertIn('система вернёт вас к форме доклада', '\n'.join(steps))
        for domain in DOMAINS:
            with self.subTest(reader_domain=domain['slug']):
                text = '\n'.join(scenario(
                    'reader', f"reader-{domain['slug']}", f"{domain['slug']}-detail",
                ).errors)
                self.assertIn('сообщите редактору', text)
        admin_text = guide_text('admin')
        for required in ('is_staff', 'is_superuser', 'activity.view_activity_report', '403', '404'):
            self.assertIn(required, admin_text)

    def test_editorial_roles_have_target_preconditions_and_screenshots(self):
        role_titles = {'admin': 'администратор', 'editor': 'редактор'}
        for role, title in role_titles.items():
            for domain in DOMAINS:
                with self.subTest(role=role, domain=domain['slug']):
                    listing = scenario(role, domain['slug'], f"{domain['slug']}-list")
                    managing = scenario(role, domain['slug'], f"{domain['slug']}-manage")
                    self.assertEqual(
                        listing.preconditions,
                        f'Вы вошли как {title}; кабинетным ролям общий реестр закрыт.',
                    )
                    self.assertEqual(
                        managing.preconditions,
                        f'У вас есть права {title}а на изменение записей этого раздела.' if title == 'редактор'
                        else 'У вас есть права администратора на изменение записей этого раздела.',
                    )
            self.assertEqual(
                scenario(role, 'reports', 'person-reports').screenshot,
                f'{role}-person-report',
            )
            cards = scenario(role, 'reports', 'cards-and-account')
            self.assertEqual(cards.screenshot, f'{role}-account')
            if role == 'admin':
                self.assertIn('вы можете открывать и другие учётные записи', cards.preconditions)
                self.assertIn('откройте из журнала активности', cards.steps[-1])
            else:
                self.assertIn('вам доступна собственная учётная запись', cards.preconditions)
                self.assertIn('других учётных записей вашей роли недоступны', cards.steps[-1])

    def test_cabinet_publication_examples_are_specific(self):
        expected = {
            'teacher': ('teacher-publications', 'Метод анализа устойчивости сети', 'подопечного курсанта'),
            'adjunct': ('adjunct-publications', 'Модель обработки экспериментальных данных', 'научного руководителя'),
            'student': ('student-publications', 'Анализ защищённости учебной сети', 'научного руководителя'),
        }
        examples = set()
        for role, (chapter_slug, title, coauthor) in expected.items():
            with self.subTest(role=role):
                example = scenario(role, chapter_slug, 'publication-create').example
                self.assertIn(title, example)
                self.assertIn(coauthor, example)
                self.assertNotIn('руководителя или подопечного', example)
                examples.add(example)
        self.assertEqual(len(examples), 3)

    def test_screenshot_audience_and_capture_users(self):
        self.assertEqual(validate_screenshot_registry(), [])
        specs = []
        for key, shot in SCREENSHOTS.items():
            with self.subTest(key=key):
                if len(shot.roles) == 1:
                    role = shot.roles[0]
                    self.assertEqual(shot.captured_by, ROLE_DEMO_USERS[role])
                if not shot.roles:
                    self.assertEqual(key, 'common-login')
                    self.assertEqual(shot.captured_by, '')
            specs.append(SimpleNamespace(key=key, user=shot.captured_by))
        self.assertEqual(validate_capture_specs(specs), [])
        wrong_specs = [
            SimpleNamespace(key=spec.key, user='ivanov' if spec.key == 'student-help' else spec.user)
            for spec in specs
        ]
        errors = validate_capture_specs(wrong_specs)
        self.assertTrue(any('student-help' in error and 'ожидается' in error for error in errors))

    def test_coverage_matrix_links_every_scenario_to_url_and_tests(self):
        rows = coverage_rows()
        expected = {(role, item.slug, scenario.slug)
                    for role in GUIDES for item in chapters_for(role) for scenario in item.scenarios}
        actual = {(row.role, row.chapter, row.scenario) for row in rows}
        self.assertEqual(actual, expected)
        self.assertEqual(len(rows), len(expected))
        for row in rows:
            with self.subTest(role=row.role, chapter=row.chapter, scenario=row.scenario):
                self.assertTrue(row.url.startswith('/'), row)
                self.assertIn(row.screenshot, SCREENSHOTS)
                self.assertIn('PageTests', row.test)
                self.assertIn('ContentTests', row.test)
                if row.scenario != 'using-help':
                    self.assertNotEqual(row.url, '/help/', row)

    def test_all_images_exist_and_have_metadata(self):
        root = Path(settings.BASE_DIR) / 'static' / 'help' / 'images'
        self.assertEqual(len(SCREENSHOTS), 84)
        for key, shot in SCREENSHOTS.items():
            with self.subTest(key=key):
                path = root / shot.filename
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 5000)
                self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
                self.assertTrue(shot.alt)
                self.assertTrue(shot.title)
                self.assertGreaterEqual(len(shot.legend), 2)
                self.assertTrue(all(shot.legend))

    def test_pdf_files_are_complete(self):
        for role, guide in GUIDES.items():
            with self.subTest(role=role):
                path = GENERATED_DIR / f'{role}.pdf'
                chapters = chapters_for(role)
                self.assertEqual(inspect_pdf(path, guide, chapters), [])
                self.assertGreater((GENERATED_DIR / f'{role}.pdf').stat().st_size, 100_000)
                text = pdf_text(path)
                if text is not None:
                    self.assertIn(' '.join(ROLE_COMMON[role]['report_example'].split()), text)
                    self.assertNotIn('Для демонстрационной среды преподаватель вводит логин ivanov', text)
                    self.assertNotIn('руководителя или подопечного', text)
                    if role != 'admin':
                        self.assertEqual(technical_terms(text), [])
                    if role == 'reader':
                        for domain in DOMAINS:
                            self.assertNotIn(' '.join(domain['delete'].split()), text)


class PageTests(HelpFixture):
    def test_anonymous_is_redirected(self):
        urls = [reverse('help:index'), reverse('help:guide', args=['editor']),
                reverse('help:chapter', args=['editor', 'getting-started']), reverse('help:pdf', args=['editor'])]
        for url in urls:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_own_pages_and_cabinet_whitelist(self):
        first_chapter = COMMON_CHAPTER_SLUGS[0]
        for role, user in self.users.items():
            self.client.force_login(user)
            for url in (reverse('help:index'), reverse('help:guide', args=[role]),
                        reverse('help:chapter', args=[role, first_chapter])):
                with self.subTest(role=role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
            response = self.client.get(reverse('help:index'))
            self.assertContains(response, f'href="{reverse("help:guide", args=[role])}"')
            self.assertContains(response, 'Справочная система')

    def test_other_role_is_closed_and_staff_can_open_all(self):
        for role in ('teacher', 'adjunct', 'student', 'reader'):
            self.client.force_login(self.users[role])
            with self.subTest(role=role):
                self.assertEqual(self.client.get(reverse('help:guide', args=['admin'])).status_code, 403)
                self.assertEqual(self.client.get(reverse('help:pdf', args=['admin'])).status_code, 403)
        for user in (self.admin, self.editor):
            self.client.force_login(user)
            for role in GUIDES:
                with self.subTest(user=user.username, role=role):
                    self.assertEqual(self.client.get(reverse('help:guide', args=[role])).status_code, 200)

    def test_menu_link_in_cabinet_and_general_sections(self):
        for user, url in ((self.teacher, self.teacher.teacher.get_absolute_url()),
                          (self.editor, reverse('core:home'))):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                response = self.client.get(url)
                self.assertContains(response, f'href="{reverse("help:index")}"')
                self.assertContains(response, 'Справка')
                self.assertContains(response, 'navbar-expand-xxl')
                self.assertContains(response, 'container-fluid')
                self.assertContains(response, 'core.css')

    def test_all_chapters_render_all_scenarios(self):
        self.client.force_login(self.editor)
        for role in GUIDES:
            for item in chapters_for(role):
                with self.subTest(role=role, chapter=item.slug):
                    response = self.client.get(reverse('help:chapter', args=[role, item.slug]))
                    self.assertEqual(response.status_code, 200)
                    for scenario in item.scenarios:
                        self.assertContains(response, scenario.title)
                        self.assertContains(response, f'id="{scenario.slug}"')
                        self.assertContains(response, scenario.image.static_path)
                        self.assertContains(response, scenario.image.alt)
                        self.assertContains(response, scenario.goal)
                        self.assertContains(response, scenario.preconditions)
                        self.assertContains(response, scenario.example)
                        self.assertContains(response, scenario.result)
                        for value in (*scenario.steps, *scenario.errors):
                            self.assertContains(response, value)
                        if scenario.related:
                            self.assertContains(response, scenario.related)
                    self.assertContains(response, reverse('help:pdf', args=[role]))

    def test_unknown_material_is_404(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get('/help/unknown/').status_code, 404)
        self.assertEqual(self.client.get(reverse('help:chapter', args=['editor', 'unknown'])).status_code, 404)

    def test_neighbour_navigation(self):
        self.client.force_login(self.editor)
        chapters = chapters_for('editor')
        response = self.client.get(reverse('help:chapter', args=['editor', chapters[1].slug]))
        self.assertContains(response, reverse('help:chapter', args=['editor', chapters[0].slug]))
        self.assertContains(response, reverse('help:chapter', args=['editor', chapters[2].slug]))


class PdfDownloadTests(HelpFixture):
    def test_download_headers_content_and_activity(self):
        self.client.force_login(self.teacher)
        url = reverse('help:pdf', args=['teacher'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        disposition = response['Content-Disposition']
        self.assertIn('attachment', disposition)
        self.assertIn('filename=', disposition)
        self.assertIn("filename*=UTF-8''", disposition)
        content = b''.join(response.streaming_content)
        response.close()
        self.assertEqual(content[:5], b'%PDF-')
        log = ActivityLog.objects.filter(user=self.teacher, path=url).latest('created_at')
        self.assertEqual(log.action, ActivityLog.Action.EXPORT)

    def test_staff_can_download_every_guide(self):
        self.client.force_login(self.editor)
        for role in GUIDES:
            with self.subTest(role=role):
                response = self.client.get(reverse('help:pdf', args=[role]))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                response.close()
