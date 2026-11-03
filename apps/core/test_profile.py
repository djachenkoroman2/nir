from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.staff.models import Teacher
from apps.staff.tests import make_editor, make_teacher
from apps.students.models import Student
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

URL = reverse('core:profile_edit')


def profile_data(**overrides):
    data = {
        'last_name': 'Новаяфамилия',
        'first_name': 'Новоеимя',
        'middle_name': 'Новоеотчество',
        'email': 'new@example.ru',
        'phone': '+7 (900) 123-45-67',
    }
    data.update(overrides)
    return data


class ProfilePersonTests(TestCase):
    def test_teacher_updates_person_and_account(self):
        teacher = make_teacher(last_name='Стараяфамилия', position=Teacher.Position.HEAD)
        user = make_teacher_user(teacher)
        self.client.force_login(user)
        response = self.client.get(URL)
        self.assertContains(response, 'name="middle_name"')
        self.assertContains(response, 'name="phone"')

        response = self.client.post(URL, profile_data())
        self.assertRedirects(response, reverse('reports:account'))
        teacher.refresh_from_db()
        user.refresh_from_db()
        for field in ('last_name', 'first_name', 'middle_name', 'email', 'phone'):
            self.assertEqual(getattr(teacher, field), profile_data()[field])
        self.assertEqual(user.last_name, teacher.last_name)
        self.assertEqual(user.first_name, teacher.first_name)
        self.assertEqual(user.email, teacher.email)
        self.assertEqual(teacher.position, Teacher.Position.HEAD)
        self.assertTrue(ActivityLog.objects.filter(
            content_type=ContentType.objects.get_for_model(teacher), object_id=teacher.pk,
            action=ActivityLog.Action.UPDATE,
        ).exists())

    def test_adjunct_updates_contacts_without_changing_study_fields(self):
        supervisor = make_teacher()
        adjunct = make_adjunct(supervisor, last_name='Стараяфамилия')
        user = make_adjunct_user(adjunct)
        topic, status = adjunct.dissertation_topic, adjunct.status
        self.client.force_login(user)
        response = self.client.post(URL, profile_data())
        self.assertRedirects(response, reverse('reports:account'))
        adjunct.refresh_from_db()
        user.refresh_from_db()
        for field in ('last_name', 'first_name', 'middle_name', 'email', 'phone'):
            self.assertEqual(getattr(adjunct, field), profile_data()[field])
        self.assertEqual(adjunct.dissertation_topic, topic)
        self.assertEqual(adjunct.status, status)
        self.assertEqual(adjunct.supervisor, supervisor)
        self.assertEqual(user.email, adjunct.email)

    def test_student_updates_name_and_account_email_only(self):
        student = make_student(last_name='Стараяфамилия', group='ИБ-21', course=3, note='Служебная заметка')
        user = make_student_user(student)
        self.client.force_login(user)
        response = self.client.get(URL)
        self.assertContains(response, 'name="middle_name"')
        self.assertNotContains(response, 'name="phone"')

        data = profile_data()
        del data['phone']
        data.update({'group': 'ДР-99', 'course': '1', 'status': Student.Status.EXPELLED, 'note': 'Попытка сменить'})
        response = self.client.post(URL, data)
        self.assertRedirects(response, reverse('reports:account'))
        student.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(student.last_name, data['last_name'])
        self.assertEqual(student.first_name, data['first_name'])
        self.assertEqual(student.middle_name, data['middle_name'])
        self.assertEqual(student.group, 'ИБ-21')
        self.assertEqual(student.course, 3)
        self.assertEqual(student.status, Student.Status.STUDYING)
        self.assertEqual(student.note, 'Служебная заметка')
        self.assertEqual(user.email, data['email'])

    def test_invalid_email_is_rejected(self):
        teacher = make_teacher(email='old@example.ru')
        user = make_teacher_user(teacher)
        user.email = teacher.email
        user.save(update_fields=['email'])
        self.client.force_login(user)
        response = self.client.post(URL, profile_data(email='not-an-email'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Введите правильный адрес электронной почты.')
        teacher.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(teacher.email, 'old@example.ru')
        self.assertEqual(user.email, 'old@example.ru')

    def test_required_name_is_rejected(self):
        student = make_student(first_name='Исходноеимя')
        user = make_student_user(student)
        self.client.force_login(user)
        data = profile_data(first_name='')
        del data['phone']
        response = self.client.post(URL, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['first_name'])
        student.refresh_from_db()
        self.assertEqual(student.first_name, 'Исходноеимя')


class ProfileAccountTests(TestCase):
    def test_every_account_without_person_can_edit_own_data(self):
        users = [
            User.objects.create_user('reader', password='secret'),
            make_editor(),
            User.objects.create_superuser('root', password='secret'),
        ]
        for index, user in enumerate(users):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(URL)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'name="middle_name"')
                self.assertNotContains(response, 'name="phone"')
                was_staff, was_superuser = user.is_staff, user.is_superuser
                response = self.client.post(URL, profile_data(
                    last_name=f'Фамилия{index}', middle_name='', phone='',
                    is_staff='on', is_superuser='on',
                ))
                self.assertRedirects(response, reverse('reports:account'))
                user.refresh_from_db()
                self.assertEqual(user.last_name, f'Фамилия{index}')
                self.assertEqual(user.first_name, 'Новоеимя')
                self.assertEqual(user.email, 'new@example.ru')
                self.assertEqual(user.is_staff, was_staff)
                self.assertEqual(user.is_superuser, was_superuser)

    def test_anonymous_is_redirected_to_login(self):
        self.assertRedirects(self.client.get(URL), f'{reverse("login")}?next={URL}')

    def test_account_page_has_edit_link_only_for_own_account(self):
        reader = User.objects.create_user('reader', password='secret')
        root = User.objects.create_superuser('root', password='secret')
        self.client.force_login(reader)
        self.assertContains(self.client.get(reverse('reports:account')), URL)

        self.client.force_login(root)
        self.assertContains(self.client.get(reverse('reports:account')), URL)
        response = self.client.get(reverse('reports:account_user', args=[reader.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, URL)
