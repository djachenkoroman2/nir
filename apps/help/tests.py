from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .content import COMMON_CHAPTERS, GUIDES, chapters_for, get_chapter, validate_content
from .coverage import coverage_rows
from .pdf import GENERATED_DIR, inspect_pdf
from .roles import accessible_guides, can_view_role, role_for_user
from .screenshots import SCREENSHOTS


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
                self.assertEqual(COMMON_CHAPTERS, chapters_for(role)[:len(COMMON_CHAPTERS)])

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
        self.assertEqual(len(SCREENSHOTS), 60)
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
                self.assertEqual(inspect_pdf(path, guide, chapters_for(role)), [])
                self.assertGreater((GENERATED_DIR / f'{role}.pdf').stat().st_size, 100_000)


class PageTests(HelpFixture):
    def test_anonymous_is_redirected(self):
        urls = [reverse('help:index'), reverse('help:guide', args=['editor']),
                reverse('help:chapter', args=['editor', 'getting-started']), reverse('help:pdf', args=['editor'])]
        for url in urls:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_own_pages_and_cabinet_whitelist(self):
        first_chapter = COMMON_CHAPTERS[0].slug
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
