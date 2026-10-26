import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.staff.tests import make_editor, make_teacher

from .models import Participant, ResearchProject


def formset_data(rows, initial=0):
    data = {
        'memberships-TOTAL_FORMS': str(len(rows)),
        'memberships-INITIAL_FORMS': str(initial),
        'memberships-MIN_NUM_FORMS': '0',
        'memberships-MAX_NUM_FORMS': '1000',
    }
    for index, row in enumerate(rows):
        for key, value in row.items():
            data[f'memberships-{index}-{key}'] = value
    return data


class ResearchProjectModelTests(TestCase):
    def test_end_date_before_start_date_is_invalid(self):
        project = ResearchProject(title='Проект', start_date=datetime.date(2026, 5, 1),
                                  end_date=datetime.date(2026, 4, 30))
        with self.assertRaises(ValidationError) as context:
            project.full_clean()
        self.assertIn('end_date', context.exception.message_dict)

    def test_end_date_is_optional(self):
        ResearchProject(title='Проект', start_date=datetime.date(2026, 5, 1)).full_clean()

    def test_teacher_cannot_participate_twice(self):
        project = ResearchProject.objects.create(title='Проект', start_date='2026-01-01')
        teacher = make_teacher()
        Participant.objects.create(project=project, teacher=teacher, role=Participant.Role.LEADER)
        with self.assertRaises(IntegrityError):
            Participant.objects.create(project=project, teacher=teacher)

    def test_leader_is_listed_first(self):
        project = ResearchProject.objects.create(title='Проект', start_date='2026-01-01')
        member = make_teacher(last_name='Абрамов')
        leader = make_teacher(last_name='Яковлев')
        Participant.objects.create(project=project, teacher=member, role=Participant.Role.MEMBER)
        Participant.objects.create(project=project, teacher=leader, role=Participant.Role.LEADER)
        self.assertEqual([m.teacher for m in project.memberships.all()], [leader, member])


class ResearchProjectAccessTests(TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(title='Цифровой двойник', start_date='2026-01-01')
        self.reader = User.objects.create_user(username='reader', password='secret')

    def test_anonymous_is_redirected_to_login(self):
        for url in (reverse('research:project_list'), self.project.get_absolute_url()):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_reader_can_view_without_edit_buttons(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse('research:project_list'))
        self.assertContains(response, 'Цифровой двойник')
        self.assertNotContains(response, reverse('research:project_create'))
        response = self.client.get(self.project.get_absolute_url())
        self.assertNotContains(response, reverse('research:project_update', args=[self.project.pk]))

    def test_reader_gets_403_on_edit_pages(self):
        self.client.force_login(self.reader)
        for url in (reverse('research:project_create'),
                    reverse('research:project_update', args=[self.project.pk]),
                    reverse('research:project_delete', args=[self.project.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_filter_by_status(self):
        ResearchProject.objects.create(title='Завершённый', start_date='2025-01-01',
                                       status=ResearchProject.Status.COMPLETED)
        self.client.force_login(self.reader)
        response = self.client.get(reverse('research:project_list'), {'status': 'completed'})
        self.assertEqual([p.title for p in response.context['researchproject_list']], ['Завершённый'])


class ResearchProjectEditTests(TestCase):
    def setUp(self):
        self.leader = make_teacher(last_name='Смирнов')
        self.member = make_teacher(last_name='Кузнецова', first_name='Мария')
        self.client.force_login(make_editor())

    def test_editor_creates_project_with_participants(self):
        data = {'title': 'Новая НИОКР', 'start_date': '2026-02-01', 'end_date': '2026-12-31',
                'status': ResearchProject.Status.IN_PROGRESS}
        data.update(formset_data([
            {'teacher': self.leader.pk, 'role': Participant.Role.LEADER},
            {'teacher': self.member.pk, 'role': Participant.Role.MEMBER},
            {'teacher': '', 'role': Participant.Role.MEMBER},
        ]))
        response = self.client.post(reverse('research:project_create'), data)
        project = ResearchProject.objects.get(title='Новая НИОКР')
        self.assertRedirects(response, project.get_absolute_url())
        self.assertEqual(project.memberships.count(), 2)
        self.assertEqual(project.memberships.first().teacher, self.leader)

    def test_editor_updates_project(self):
        project = ResearchProject.objects.create(title='Старое название', start_date='2026-01-01')
        membership = Participant.objects.create(project=project, teacher=self.leader)
        data = {'title': 'Новое название', 'start_date': '2026-01-01', 'status': ResearchProject.Status.COMPLETED}
        data.update(formset_data([
            {'id': membership.pk, 'teacher': self.leader.pk, 'role': Participant.Role.LEADER},
        ], initial=1))
        response = self.client.post(reverse('research:project_update', args=[project.pk]), data)
        self.assertRedirects(response, project.get_absolute_url())
        project.refresh_from_db()
        self.assertEqual(project.title, 'Новое название')
        self.assertEqual(project.memberships.get().role, Participant.Role.LEADER)

    def test_duplicate_participant_in_form_is_rejected(self):
        data = {'title': 'Дубли', 'start_date': '2026-01-01', 'status': ResearchProject.Status.PLANNED}
        data.update(formset_data([
            {'teacher': self.leader.pk, 'role': Participant.Role.LEADER},
            {'teacher': self.leader.pk, 'role': Participant.Role.MEMBER},
        ]))
        response = self.client.post(reverse('research:project_create'), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ResearchProject.objects.filter(title='Дубли').exists())
        self.assertTrue(response.context['formset'].non_form_errors())

    def test_invalid_dates_in_form_are_rejected(self):
        data = {'title': 'Даты', 'start_date': '2026-05-01', 'end_date': '2026-04-01',
                'status': ResearchProject.Status.PLANNED}
        data.update(formset_data([]))
        response = self.client.post(reverse('research:project_create'), data)
        self.assertContains(response, 'Дата окончания не может быть раньше даты начала.')
        self.assertFalse(ResearchProject.objects.filter(title='Даты').exists())

    def test_inactive_teacher_is_not_offered_for_new_participants(self):
        retired = make_teacher(last_name='Уволенный', is_active=False)
        response = self.client.get(reverse('research:project_create'))
        teachers = response.context['formset'].forms[0].fields['teacher'].queryset
        self.assertNotIn(retired, teachers)
        self.assertIn(self.leader, teachers)


class ResearchProjectSearchTests(TestCase):
    def test_search_is_case_insensitive_for_cyrillic(self):
        ResearchProject.objects.create(title='Цифровой двойник предприятия', start_date='2026-01-01')
        ResearchProject.objects.create(title='Другая работа', start_date='2026-01-01')
        self.client.force_login(User.objects.create_user(username='reader', password='secret'))
        response = self.client.get(reverse('research:project_list'), {'q': 'ЦИФРОВОЙ Предприятия'})
        self.assertEqual([p.title for p in response.context['researchproject_list']],
                         ['Цифровой двойник предприятия'])
