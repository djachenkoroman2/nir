import datetime

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.core.testing import formset_data
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.forms import PublicationAuthorFormSet
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.tests import make_editor, make_teacher

from .models import Student, StudentAchievement


def make_student(**kwargs):
    defaults = {'last_name': 'Курсантов', 'first_name': 'Пётр', 'middle_name': 'Ильич', 'group': 'ИБ-21', 'course': 2}
    defaults.update(kwargs)
    return Student.objects.create(**defaults)


def make_achievement(student, **kwargs):
    defaults = {'kind': StudentAchievement.Kind.OLYMPIAD, 'level': StudentAchievement.Level.NATIONAL,
                'title': 'Олимпиада', 'result': 'диплом I степени', 'date': datetime.date(2026, 4, 1)}
    defaults.update(kwargs)
    return StudentAchievement.objects.create(student=student, **defaults)


def make_teacher_user(teacher, username='teacher'):
    user = User.objects.create_user(username=username, password='secret')
    user.groups.add(Group.objects.get(name='Преподаватели'))
    teacher.user = user
    teacher.save()
    return user


def publication_with_student(student, title='Статья курсанта', **fields):
    publication = Publication.objects.create(title=title, year=2026, **fields)
    PublicationAuthor.objects.create(publication=publication, student=student, order=1)
    return publication


class StudentModelTests(TestCase):
    def test_short_name(self):
        self.assertEqual(str(make_student()), 'Курсантов П. И.')

    def test_course_must_be_from_1_to_6(self):
        for course, valid in [(0, False), (1, True), (6, True), (7, False)]:
            with self.subTest(course=course):
                student = Student(last_name='А', first_name='Б', group='ИБ-11', course=course)
                if valid:
                    student.full_clean()
                else:
                    with self.assertRaises(ValidationError):
                        student.full_clean()

    def test_author_is_exactly_one_of_teacher_student_external(self):
        teacher, student = make_teacher(), make_student()
        publication = Publication.objects.create(title='Статья', year=2026)
        cases = [
            ({'teacher': teacher}, True),
            ({'student': student}, True),
            ({'external_name': 'Внешний А. А.'}, True),
            ({}, False),
            ({'teacher': teacher, 'student': student}, False),
            ({'student': student, 'external_name': 'Внешний А. А.'}, False),
        ]
        for fields, valid in cases:
            with self.subTest(fields=list(fields)):
                author = PublicationAuthor(publication=publication, **fields)
                if valid:
                    author.full_clean()
                else:
                    with self.assertRaises(ValidationError):
                        author.full_clean()

    def test_author_str_for_student(self):
        author = PublicationAuthor(student=make_student())
        self.assertEqual(str(author), 'Курсантов П. И.')


class AuthorFormSetTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.student = make_student()
        self.publication = Publication.objects.create(title='Статья', year=2026)

    def formset(self, rows):
        return PublicationAuthorFormSet(formset_data('authors', rows), instance=self.publication)

    def test_saves_student_author_in_order(self):
        formset = self.formset([{'teacher': self.teacher.pk}, {'student': self.student.pk}])
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        authors = list(self.publication.authors.all())
        self.assertEqual([(a.teacher, a.student, a.order) for a in authors],
                         [(self.teacher, None, 1), (None, self.student, 2)])

    def test_student_alone_is_enough(self):
        formset = self.formset([{'student': self.student.pk}])
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_duplicate_student_is_rejected(self):
        formset = self.formset([{'student': self.student.pk}, {'student': self.student.pk}])
        self.assertFalse(formset.is_valid())
        self.assertIn('Один и тот же курсант указан несколько раз.', formset.non_form_errors())

    def test_teacher_and_student_in_one_row_is_rejected(self):
        formset = self.formset([{'teacher': self.teacher.pk, 'student': self.student.pk}])
        self.assertFalse(formset.is_valid())

    def test_expelled_student_is_not_offered_but_kept_in_saved_rows(self):
        expelled = make_student(last_name='Отчисленный', status=Student.Status.EXPELLED)
        form = PublicationAuthorFormSet(instance=self.publication).forms[0]
        self.assertNotIn(expelled, form.fields['student'].queryset)
        self.assertIn(self.student, form.fields['student'].queryset)

        PublicationAuthor.objects.create(publication=self.publication, student=expelled, order=1)
        saved_form = PublicationAuthorFormSet(instance=self.publication).forms[0]
        self.assertIn(expelled, saved_form.fields['student'].queryset)

    def test_expelled_student_cannot_be_posted(self):
        expelled = make_student(last_name='Отчисленный', status=Student.Status.EXPELLED)
        self.assertFalse(self.formset([{'student': expelled.pk}]).is_valid())


class StudentListTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        self.supervisor = make_teacher(last_name='Руководителев')
        self.first = make_student(last_name='Первый', course=1, group='ИБ-11', supervisor=self.supervisor)
        self.second = make_student(last_name='Второй', course=3, group='ПИ-31')
        self.graduated = make_student(last_name='Выпускник', course=5, group='ИБ-51',
                                      status=Student.Status.GRADUATED)
        publication_with_student(self.first, 'Первая')
        publication_with_student(self.first, 'Вторая')
        make_achievement(self.first)

    def names(self, **params):
        response = self.client.get(reverse('students:student_list'), params)
        self.assertEqual(response.status_code, 200)
        return [student.last_name for student in response.context['student_list']]

    def test_counts_are_annotated(self):
        response = self.client.get(reverse('students:student_list'))
        rows = {s.pk: s for s in response.context['student_list']}
        self.assertEqual((rows[self.first.pk].publication_count, rows[self.first.pk].achievement_count), (2, 1))
        self.assertEqual((rows[self.second.pk].publication_count, rows[self.second.pk].achievement_count), (0, 0))

    def test_studying_by_default_and_all_statuses(self):
        self.assertEqual(self.names(), ['Первый', 'Второй'])
        self.assertEqual(self.names(status='graduated'), ['Выпускник'])
        self.assertEqual(self.names(status='all'), ['Первый', 'Второй', 'Выпускник'])

    def test_filters(self):
        self.assertEqual(self.names(course=3), ['Второй'])
        self.assertEqual(self.names(group='ИБ-11'), ['Первый'])
        self.assertEqual(self.names(supervisor=self.supervisor.pk), ['Первый'])
        self.assertEqual(self.names(q='пи-31'), ['Второй'])
        self.assertEqual(self.names(q='первый'), ['Первый'])

    def test_no_queries_per_row(self):
        for index in range(5):
            student = make_student(last_name=f'Курсант{index}', supervisor=self.supervisor)
            publication_with_student(student, f'Статья {index}')
        # Сессия, пользователь, счётчик, пункт «Мои задачи» в шапке, два запроса прав, группы, руководители,
        # страница — без запросов в цикле.
        with self.assertNumQueries(9):
            self.client.get(reverse('students:student_list'))


class StudentDetailTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        self.student = make_student()
        self.teacher = make_teacher()

    def test_shows_publications_reports_ip_achievements_and_summary(self):
        vak = publication_with_student(self.student, 'Статья ВАК', vak='K2', rinc=True)
        publication_with_student(self.student, 'Статья Scopus', scopus=True, wos=True)
        Publication.objects.create(title='Чужая статья', year=2026)
        conference = Conference.objects.create(title='Конференция', level='national',
                                               start_date=datetime.date(2026, 5, 1))
        report = Report.objects.create(conference=conference, title='Доклад курсанта')
        ReportSpeaker.objects.create(report=report, student=self.student, order=1)
        item = IntellectualProperty.objects.create(kind='software', title='Программа курсанта', number='1',
                                                   registration_date=datetime.date(2026, 3, 1))
        IntellectualPropertyAuthor.objects.create(intellectual_property=item, student=self.student, order=1)
        make_achievement(self.student, title='Олимпиада 2026')
        make_achievement(self.student, title='Конкурс 2025', kind='contest', level='international',
                         date=datetime.date(2025, 11, 1))

        response = self.client.get(self.student.get_absolute_url())
        self.assertContains(response, 'Статья ВАК')
        self.assertNotContains(response, 'Чужая статья')
        self.assertContains(response, 'Доклад курсанта')
        self.assertContains(response, 'Программа курсанта')
        self.assertContains(response, 'Олимпиада 2026')
        self.assertContains(response, 'Конкурс 2025')
        self.assertEqual(response.context['publication_stats'],
                         {'total': 2, 'vak': 1, 'rinc': 1, 'scopus': 1, 'wos': 1})
        levels = dict(response.context['achievement_levels'])
        self.assertEqual((levels['всероссийский'], levels['международный'], levels['вузовский']), (1, 1, 0))
        self.assertTrue(vak.authors.get().student_id)

    def test_student_author_is_linked_on_publication_page(self):
        publication = publication_with_student(self.student)
        response = self.client.get(publication.get_absolute_url())
        self.assertContains(response, f'href="{self.student.get_absolute_url()}"')
        self.assertContains(response, 'курсант</span>')

    def test_teacher_card_shows_supervised_students_and_achievements(self):
        self.student.supervisor = self.teacher
        self.student.save()
        make_achievement(self.student, title='Олимпиада под руководством', supervisor=self.teacher)
        response = self.client.get(self.teacher.get_absolute_url())
        self.assertContains(response, 'Научное руководство курсантами')
        self.assertContains(response, self.student.full_name)
        self.assertContains(response, 'Олимпиада под руководством')


class DeleteProtectionTests(TestCase):
    def setUp(self):
        self.client.force_login(make_editor())
        self.teacher = make_teacher()
        self.student = make_student(supervisor=self.teacher)

    def test_student_with_publications_cannot_be_deleted(self):
        publication_with_student(self.student)
        response = self.client.get(reverse('students:student_delete', args=[self.student.pk]))
        self.assertTrue(response.context['delete_blocked'])
        response = self.client.post(reverse('students:student_delete', args=[self.student.pk]), follow=True)
        self.assertContains(response, 'Нельзя удалить курсанта')
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_student_without_publications_is_deleted_with_achievements(self):
        make_achievement(self.student)
        self.client.post(reverse('students:student_delete', args=[self.student.pk]))
        self.assertFalse(Student.objects.exists())
        self.assertFalse(StudentAchievement.objects.exists())

    def test_teacher_with_students_cannot_be_deleted(self):
        self.assertTrue(self.teacher.has_protected_relations())
        response = self.client.post(reverse('staff:teacher_delete', args=[self.teacher.pk]), follow=True)
        self.assertContains(response, 'руководит научной работой курсантов')
        self.assertTrue(type(self.teacher).objects.filter(pk=self.teacher.pk).exists())


class PermissionTests(TestCase):
    def setUp(self):
        self.supervisor = make_teacher(last_name='Руководителев')
        self.other = make_teacher(last_name='Чужой')
        self.student = make_student(supervisor=self.supervisor)
        self.achievement = make_achievement(self.student)
        self.urls = {
            'create': reverse('students:student_create'),
            'update': reverse('students:student_update', args=[self.student.pk]),
            'delete': reverse('students:student_delete', args=[self.student.pk]),
            'achievement_create': reverse('students:achievement_create', args=[self.student.pk]),
            'achievement_update': reverse('students:achievement_update', args=[self.achievement.pk]),
            'achievement_delete': reverse('students:achievement_delete', args=[self.achievement.pk]),
        }

    def statuses(self):
        return {name: self.client.get(url).status_code for name, url in self.urls.items()}

    def test_anonymous_is_redirected_to_login(self):
        for url in [reverse('students:student_list'), self.student.get_absolute_url(), *self.urls.values()]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response.url)

    def test_editor_can_do_everything(self):
        self.client.force_login(make_editor())
        self.assertEqual(set(self.statuses().values()), {200})

    def test_supervisor_edits_own_student_and_achievements(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        self.assertEqual(self.statuses(), {
            'create': 403, 'update': 200, 'delete': 403,
            'achievement_create': 200, 'achievement_update': 200, 'achievement_delete': 200,
        })
        response = self.client.get(self.student.get_absolute_url())
        self.assertContains(response, 'Добавить достижение')
        self.assertNotContains(response, self.urls['delete'])

    def test_supervisor_adds_achievement_with_default_supervisor(self):
        self.client.force_login(make_teacher_user(self.supervisor))
        response = self.client.get(self.urls['achievement_create'])
        self.assertEqual(response.context['form'].initial['supervisor'], self.supervisor)
        response = self.client.post(self.urls['achievement_create'], {
            'kind': 'contest', 'level': 'regional', 'title': 'Конкурс', 'result': 'победитель',
            'date': '2026-09-01', 'supervisor': self.supervisor.pk,
        })
        self.assertRedirects(response, self.student.get_absolute_url())
        self.assertTrue(self.student.achievements.filter(title='Конкурс').exists())

    def test_other_teacher_only_views(self):
        self.client.force_login(make_teacher_user(self.other))
        self.assertEqual(set(self.statuses().values()), {403})
        self.assertEqual(self.client.get(self.student.get_absolute_url()).status_code, 200)
        response = self.client.post(self.urls['achievement_delete'])
        self.assertEqual(response.status_code, 403)
        self.assertTrue(StudentAchievement.objects.filter(pk=self.achievement.pk).exists())

    def test_teacher_can_add_student_as_coauthor(self):
        self.client.force_login(make_teacher_user(self.other))
        data = {'kind': 'article', 'title': 'Совместная статья', 'year': 2026}
        data.update(formset_data('authors', [{'teacher': self.other.pk}, {'student': self.student.pk}]))
        response = self.client.post(reverse('publications:publication_create'), data)
        publication = Publication.objects.get(title='Совместная статья')
        self.assertRedirects(response, publication.get_absolute_url())
        self.assertTrue(publication.authors.filter(student=self.student).exists())
