from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.core.testing import formset_data
from apps.publications.models import Publication, PublicationAuthor
from apps.research.models import ResearchProject
from apps.staff.tests import make_editor, make_teacher


class AuthFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ivanov', password='secret', first_name='Иван')

    def test_home_redirects_anonymous_to_login(self):
        response = self.client.get(reverse('core:home'))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_login_success_shows_greeting(self):
        response = self.client.post(reverse('login'), {'username': 'ivanov', 'password': 'secret'}, follow=True)
        self.assertContains(response, 'Здравствуйте, Иван!')

    def test_login_failure_shows_error(self):
        response = self.client.post(reverse('login'), {'username': 'ivanov', 'password': 'wrong'})
        self.assertContains(response, 'Неверный логин или пароль')

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))


class TeacherGroupTests(TestCase):
    """Пользователь из группы «Преподаватели» ведёт только свои публикации, РИД и доклады."""

    def setUp(self):
        self.user = User.objects.create_user(username='smirnov', password='secret')
        self.user.groups.add(Group.objects.get(name='Преподаватели'))
        self.me = make_teacher(last_name='Смирнов', user=self.user)
        self.colleague = make_teacher(last_name='Козлов')

        self.mine = Publication.objects.create(title='Моя статья', year=2026)
        PublicationAuthor.objects.create(publication=self.mine, teacher=self.me)
        self.foreign = Publication.objects.create(title='Чужая статья', year=2026)
        PublicationAuthor.objects.create(publication=self.foreign, teacher=self.colleague)

        self.conference = Conference.objects.create(title='Конференция', level='national', start_date='2026-05-01')
        self.my_report = Report.objects.create(conference=self.conference, title='Мой доклад')
        ReportSpeaker.objects.create(report=self.my_report, teacher=self.me)
        self.foreign_report = Report.objects.create(conference=self.conference, title='Чужой доклад')
        ReportSpeaker.objects.create(report=self.foreign_report, teacher=self.colleague)

        self.client.force_login(self.user)

    def publication_data(self, authors, title='Новая статья'):
        data = {'kind': 'article', 'title': title, 'year': '2026'}
        data.update(formset_data('authors', authors))
        return data

    def test_can_edit_and_delete_own_publication_only(self):
        self.assertEqual(self.client.get(reverse('publications:publication_update', args=[self.mine.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('publications:publication_delete', args=[self.mine.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('publications:publication_update', args=[self.foreign.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('publications:publication_delete', args=[self.foreign.pk])).status_code, 403)

    def test_edit_buttons_only_on_own_publication(self):
        mine = self.client.get(self.mine.get_absolute_url())
        self.assertContains(mine, reverse('publications:publication_update', args=[self.mine.pk]))
        foreign = self.client.get(self.foreign.get_absolute_url())
        self.assertNotContains(foreign, reverse('publications:publication_update', args=[self.foreign.pk]))
        self.assertContains(self.client.get(reverse('publications:publication_list')),
                            reverse('publications:publication_create'))

    def test_create_form_is_prefilled_with_self(self):
        response = self.client.get(reverse('publications:publication_create'))
        self.assertEqual(response.context['formset'].forms[0].initial.get('teacher'), self.me.pk)

    def test_creates_publication_with_self_as_author(self):
        response = self.client.post(reverse('publications:publication_create'), self.publication_data([
            {'teacher': self.me.pk, 'external_name': ''},
            {'teacher': '', 'external_name': 'Соавтор С. С.'},
        ]))
        publication = Publication.objects.get(title='Новая статья')
        self.assertRedirects(response, publication.get_absolute_url())
        self.assertTrue(publication.is_authored_by(self.me))

    def test_cannot_create_publication_without_self(self):
        response = self.client.post(reverse('publications:publication_create'), self.publication_data([
            {'teacher': self.colleague.pk, 'external_name': ''},
        ]))
        self.assertContains(response, 'Укажите среди авторов себя')
        self.assertFalse(Publication.objects.filter(title='Новая статья').exists())

    def test_cannot_remove_self_from_own_publication(self):
        author = self.mine.authors.get()
        data = {'kind': 'article', 'title': 'Моя статья', 'year': '2026'}
        data.update(formset_data('authors', [
            {'id': author.pk, 'teacher': self.me.pk, 'external_name': '', 'DELETE': 'on'},
            {'teacher': self.colleague.pk, 'external_name': ''},
        ], initial=1))
        response = self.client.post(reverse('publications:publication_update', args=[self.mine.pk]), data)
        self.assertContains(response, 'Укажите среди авторов себя')
        self.assertTrue(self.mine.is_authored_by(self.me))

    def test_reports(self):
        self.assertEqual(self.client.get(reverse('conferences:report_update', args=[self.my_report.pk])).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('conferences:report_update', args=[self.foreign_report.pk])).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse('conferences:report_create', args=[self.conference.pk])).status_code, 200
        )
        page = self.client.get(self.conference.get_absolute_url())
        self.assertContains(page, reverse('conferences:report_update', args=[self.my_report.pk]))
        self.assertNotContains(page, reverse('conferences:report_update', args=[self.foreign_report.pk]))

    def test_can_add_but_not_edit_conference(self):
        self.assertEqual(self.client.get(reverse('conferences:conference_create')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('conferences:conference_update', args=[self.conference.pk])).status_code, 403
        )

    def test_teachers_and_research_are_read_only(self):
        project = ResearchProject.objects.create(title='НИОКР', start_date='2026-01-01')
        for url in (reverse('staff:teacher_create'), reverse('staff:teacher_update', args=[self.me.pk]),
                    reverse('research:project_create'), reverse('research:project_update', args=[project.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_group_member_without_teacher_card_cannot_add(self):
        self.me.user = None
        self.me.save()
        self.assertEqual(self.client.get(reverse('publications:publication_create')).status_code, 403)
        self.assertNotContains(self.client.get(reverse('publications:publication_list')),
                               reverse('publications:publication_create'))

    def test_editor_is_not_restricted_to_own_records(self):
        self.client.force_login(make_editor())
        self.assertEqual(
            self.client.get(reverse('publications:publication_update', args=[self.foreign.pk])).status_code, 200
        )
        response = self.client.post(reverse('publications:publication_create'), self.publication_data([
            {'teacher': self.colleague.pk, 'external_name': ''},
        ], title='От редактора'))
        self.assertEqual(response.status_code, 302)
