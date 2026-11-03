import datetime
from unittest import mock

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .models import CooperationContract


def make_contract(**kwargs):
    defaults = {
        'title': 'Совместное исследование',
        'number': 'НТС-001',
        'organization': 'ООО «Научные технологии»',
        'subject': 'Совместная разработка методов анализа данных',
        'start_date': datetime.date(2026, 1, 1),
    }
    defaults.update(kwargs)
    return CooperationContract.objects.create(**defaults)


class CooperationContractModelTests(TestCase):
    def test_indefinite_contract_and_string(self):
        contract = make_contract(end_date=None)
        contract.full_clean()
        self.assertTrue(contract.is_indefinite)
        self.assertEqual(str(contract), 'Совместное исследование — ООО «Научные технологии»')
        self.assertEqual(contract.term_display, 'с 01.01.2026, бессрочно')

    def test_number_is_optional(self):
        make_contract(number='').full_clean()

    def test_required_fields(self):
        contract = CooperationContract(number='', title='', organization='', subject='', start_date=None)
        with self.assertRaises(ValidationError) as context:
            contract.full_clean()
        for field in ('title', 'organization', 'subject', 'start_date'):
            self.assertIn(field, context.exception.message_dict)

    def test_end_date_before_start_is_invalid(self):
        contract = make_contract(start_date=datetime.date(2026, 5, 1), end_date=datetime.date(2026, 4, 30))
        with self.assertRaises(ValidationError) as context:
            contract.full_clean()
        self.assertIn('end_date', context.exception.message_dict)

    def test_same_start_and_end_date_is_allowed(self):
        day = datetime.date(2026, 5, 1)
        contract = make_contract(start_date=day, end_date=day)
        contract.full_clean()
        self.assertEqual(contract.term_display, '01.05.2026 — 01.05.2026')

    def test_computed_states(self):
        today = datetime.date(2026, 6, 1)
        cases = [
            (CooperationContract.State.UPCOMING, datetime.date(2026, 6, 2), None),
            (CooperationContract.State.ACTIVE, datetime.date(2026, 1, 1), datetime.date(2026, 6, 1)),
            (CooperationContract.State.ACTIVE, datetime.date(2026, 1, 1), None),
            (CooperationContract.State.FINISHED, datetime.date(2026, 1, 1), datetime.date(2026, 5, 31)),
        ]
        with mock.patch('apps.cooperation.models.timezone.localdate', return_value=today):
            for expected, start, end in cases:
                with self.subTest(expected=expected):
                    contract = make_contract(start_date=start, end_date=end)
                    self.assertEqual(contract.state, expected)
                    self.assertEqual(contract.get_state_display(), expected.label)


class CooperationContractAccessTests(TestCase):
    def setUp(self):
        self.contract = make_contract()
        self.reader = User.objects.create_user('reader', password='secret')
        self.editor = make_editor()

    def test_anonymous_is_redirected_to_login(self):
        for url in (reverse('cooperation:contract_list'), self.contract.get_absolute_url(),
                    reverse('cooperation:contract_create')):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_reader_can_view_but_not_change(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse('cooperation:contract_list'))
        self.assertContains(response, self.contract.title)
        self.assertNotContains(response, reverse('cooperation:contract_create'))
        response = self.client.get(self.contract.get_absolute_url())
        self.assertContains(response, self.contract.subject)
        self.assertNotContains(response, reverse('cooperation:contract_update', args=[self.contract.pk]))
        for url in (reverse('cooperation:contract_create'),
                    reverse('cooperation:contract_update', args=[self.contract.pk]),
                    reverse('cooperation:contract_delete', args=[self.contract.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_without_permissions_cannot_change(self):
        user = User.objects.create_user('staffer', password='secret', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('cooperation:contract_create')).status_code, 403)

    def test_cabinet_roles_get_403(self):
        teacher = make_teacher()
        users = [
            make_teacher_user(teacher),
            make_adjunct_user(make_adjunct(teacher)),
            make_student_user(make_student(supervisor=teacher)),
        ]
        for user in users:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(reverse('cooperation:contract_list')).status_code, 403)
                self.assertEqual(self.client.get(self.contract.get_absolute_url()).status_code, 403)

    def test_editor_crud_and_activity_log(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('cooperation:contract_create'), {
            'title': 'Новый договор', 'number': 'НТС-100', 'organization': 'АО «Институт»',
            'subject': 'Предмет нового договора', 'start_date': '2026-02-01', 'end_date': '',
        })
        contract = CooperationContract.objects.get(title='Новый договор')
        self.assertRedirects(response, contract.get_absolute_url())
        self.assertTrue(contract.is_indefinite)

        response = self.client.post(reverse('cooperation:contract_update', args=[contract.pk]), {
            'title': 'Изменённый договор', 'number': 'НТС-100', 'organization': 'АО «Институт»',
            'subject': contract.subject, 'start_date': '2026-02-01', 'end_date': '2026-12-31',
        })
        self.assertRedirects(response, contract.get_absolute_url())
        contract.refresh_from_db()
        self.assertEqual(contract.title, 'Изменённый договор')
        self.assertEqual(contract.end_date, datetime.date(2026, 12, 31))
        content_type = ContentType.objects.get_for_model(contract)
        for action in (ActivityLog.Action.CREATE, ActivityLog.Action.UPDATE):
            self.assertTrue(ActivityLog.objects.filter(
                content_type=content_type, object_id=contract.pk, action=action,
            ).exists())

        response = self.client.post(reverse('cooperation:contract_delete', args=[contract.pk]))
        self.assertRedirects(response, reverse('cooperation:contract_list'))
        self.assertFalse(CooperationContract.objects.filter(pk=contract.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(
            content_type=content_type, object_id=contract.pk, action=ActivityLog.Action.DELETE,
        ).exists())

    def test_invalid_dates_in_form_are_rejected(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse('cooperation:contract_create'), {
            'title': 'Неверные даты', 'number': '', 'organization': 'Организация', 'subject': 'Предмет',
            'start_date': '2026-05-01', 'end_date': '2026-04-01',
        })
        self.assertContains(response, 'Дата окончания не может быть раньше даты начала.')
        self.assertFalse(CooperationContract.objects.filter(title='Неверные даты').exists())

    def test_model_is_registered_in_admin(self):
        self.assertIn(CooperationContract, admin.site._registry)


class CooperationContractListTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.active = make_contract(
            title='Цифровой двойник', number='НТС-123', organization='Академия технологий',
            subject='Моделирование производственной линии',
            start_date=self.today - datetime.timedelta(days=10), end_date=self.today + datetime.timedelta(days=10),
        )
        self.indefinite = make_contract(title='Бессрочный', start_date=self.today - datetime.timedelta(days=20))
        self.finished = make_contract(
            title='Завершённый', start_date=self.today - datetime.timedelta(days=100),
            end_date=self.today - datetime.timedelta(days=1),
        )
        self.upcoming = make_contract(title='Планируемый', start_date=self.today + datetime.timedelta(days=1))
        self.client.force_login(User.objects.create_user('reader', password='secret'))

    def contracts(self, **params):
        response = self.client.get(reverse('cooperation:contract_list'), params)
        return set(response.context['cooperationcontract_list'])

    def test_search_all_fields_case_insensitive(self):
        for query in ('ЦИФРОВОЙ', 'нтс-123', 'АКАДЕМИЯ', 'моделирование'):
            with self.subTest(query=query):
                self.assertEqual(self.contracts(q=query), {self.active})

    def test_filters(self):
        cases = {
            'active': {self.active, self.indefinite},
            'finished': {self.finished},
            'indefinite': {self.indefinite, self.upcoming},
            'upcoming': {self.upcoming},
            '': {self.active, self.indefinite, self.finished, self.upcoming},
        }
        for state, expected in cases.items():
            with self.subTest(state=state):
                self.assertEqual(self.contracts(state=state), expected)

    def test_home_contains_section(self):
        response = self.client.get(reverse('core:home'))
        self.assertContains(response, 'Сотрудничество')
        self.assertContains(response, reverse('cooperation:contract_list'))
