from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.research.models import Participant, ResearchProject

from .models import Teacher


def make_teacher(**kwargs):
    defaults = {'last_name': 'Иванов', 'first_name': 'Иван', 'middle_name': 'Иванович',
                'position': Teacher.Position.ASSOCIATE_PROFESSOR}
    defaults.update(kwargs)
    return Teacher.objects.create(**defaults)


def make_editor(username='editor'):
    user = User.objects.create_user(username=username, password='secret', is_staff=True)
    user.groups.add(Group.objects.get(name='Редакторы НИР'))
    return user


class TeacherModelTests(TestCase):
    def test_short_name(self):
        self.assertEqual(str(make_teacher()), 'Иванов И. И.')

    def test_short_name_without_middle_name(self):
        self.assertEqual(str(make_teacher(middle_name='')), 'Иванов И.')


class TeacherAccessTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.reader = User.objects.create_user(username='reader', password='secret')
        self.editor = make_editor()

    def test_anonymous_is_redirected_to_login(self):
        for url in (reverse('staff:teacher_list'), self.teacher.get_absolute_url(),
                    reverse('staff:teacher_create')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_reader_can_view_without_edit_buttons(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse('staff:teacher_list'))
        self.assertContains(response, 'Иванов Иван Иванович')
        self.assertNotContains(response, reverse('staff:teacher_create'))
        response = self.client.get(self.teacher.get_absolute_url())
        self.assertNotContains(response, reverse('staff:teacher_update', args=[self.teacher.pk]))

    def test_reader_gets_403_on_edit_pages(self):
        self.client.force_login(self.reader)
        for url in (reverse('staff:teacher_create'),
                    reverse('staff:teacher_update', args=[self.teacher.pk]),
                    reverse('staff:teacher_delete', args=[self.teacher.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_without_permissions_gets_403(self):
        user = User.objects.create_user(username='staffer', password='secret', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('staff:teacher_create')).status_code, 403)

    def test_editor_can_create_and_update(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('staff:teacher_create'), {
            'last_name': 'Петрова', 'first_name': 'Анна', 'position': Teacher.Position.PROFESSOR,
            'degree': Teacher.Degree.DOCTOR, 'academic_title': Teacher.AcademicTitle.PROFESSOR,
            'is_active': 'on',
        })
        teacher = Teacher.objects.get(last_name='Петрова')
        self.assertRedirects(response, teacher.get_absolute_url())

        response = self.client.post(reverse('staff:teacher_update', args=[teacher.pk]), {
            'last_name': 'Петрова', 'first_name': 'Анна', 'position': Teacher.Position.HEAD,
            'degree': Teacher.Degree.DOCTOR, 'academic_title': Teacher.AcademicTitle.PROFESSOR,
        })
        self.assertRedirects(response, teacher.get_absolute_url())
        teacher.refresh_from_db()
        self.assertEqual(teacher.position, Teacher.Position.HEAD)
        self.assertFalse(teacher.is_active)

    def test_teacher_in_project_is_not_deleted(self):
        project = ResearchProject.objects.create(title='Проект', start_date='2026-01-01')
        Participant.objects.create(project=project, teacher=self.teacher)
        self.client.force_login(self.editor)
        response = self.client.post(reverse('staff:teacher_delete', args=[self.teacher.pk]))
        self.assertRedirects(response, self.teacher.get_absolute_url())
        self.assertTrue(Teacher.objects.filter(pk=self.teacher.pk).exists())


class TeacherListFilterTests(TestCase):
    def setUp(self):
        make_teacher()
        make_teacher(last_name='Сидоров', first_name='Пётр', is_active=False)
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))

    def test_search_by_name(self):
        response = self.client.get(reverse('staff:teacher_list'), {'q': 'сидор'})
        self.assertEqual([t.last_name for t in response.context['teacher_list']], ['Сидоров'])

    def test_filter_by_activity(self):
        response = self.client.get(reverse('staff:teacher_list'), {'active': '1'})
        self.assertEqual([t.last_name for t in response.context['teacher_list']], ['Иванов'])
