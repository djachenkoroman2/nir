import datetime
from urllib.parse import unquote

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.cooperation.models import CooperationContract
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .cooperation import build_cooperation_report, cooperation_document, cooperation_filenames
from .docx_common import DOCX_TYPE
from .test_person_reports import docx_text
from .works import Period, contracts

URL = reverse('reports:cooperation')


def make_contract(title, start, end=None, **kwargs):
    return CooperationContract.objects.create(
        title=title,
        number=kwargs.pop('number', title),
        organization=kwargs.pop('organization', f'Организация «{title}»'),
        subject=kwargs.pop('subject', f'Предмет договора «{title}»'),
        start_date=start,
        end_date=end,
        **kwargs,
    )


class CooperationReportBuildTests(TestCase):
    def setUp(self):
        self.period = Period(2025, 2026)
        self.old = make_contract('До периода', datetime.date(2023, 1, 1), datetime.date(2024, 12, 31))
        self.left_boundary = make_contract('На левой границе', datetime.date(2024, 1, 1),
                                           datetime.date(2025, 1, 1))
        self.crossing = make_contract('Переходящий', datetime.date(2025, 6, 1), datetime.date(2026, 5, 31))
        self.right_boundary = make_contract('На правой границе', datetime.date(2026, 12, 31),
                                            datetime.date(2027, 1, 1))
        self.indefinite = make_contract('Бессрочный', datetime.date(2024, 1, 1))
        self.future = make_contract('После периода', datetime.date(2027, 1, 1))
        self.future_indefinite = make_contract('Бессрочный в будущем', datetime.date(2027, 1, 1))

    def test_period_overlap_and_boundaries(self):
        selected = set(contracts(self.period))
        self.assertEqual(selected, {self.left_boundary, self.crossing, self.right_boundary, self.indefinite})
        self.assertNotIn(self.old, selected)
        self.assertNotIn(self.future, selected)
        self.assertNotIn(self.future_indefinite, selected)
        self.assertEqual(set(contracts(Period(2025, 2025))),
                         {self.left_boundary, self.crossing, self.indefinite})
        self.assertEqual(set(contracts(Period(2023, 2023))), {self.old})
        self.assertEqual(set(contracts(Period(2022, 2022))), set())

    def test_report_totals_order_and_empty_period(self):
        report = build_cooperation_report(self.period)
        self.assertEqual(len(report.contracts), 4)
        self.assertEqual(report.indefinite_count, 1)
        starts = [contract.start_date for contract in report.contracts]
        self.assertEqual(starts, sorted(starts))
        empty = build_cooperation_report(Period(2020, 2020))
        self.assertEqual(empty.contracts, [])
        self.assertEqual(empty.indefinite_count, 0)

    def test_document_and_filenames(self):
        report = build_cooperation_report(self.period)
        document = cooperation_document(report)
        self.assertTrue(document.landscape)
        table = document.sections[0].table
        self.assertEqual(len(table.rows), 4)
        self.assertEqual(sum(len(row.cells) for row in table.rows), 4 * 7)
        self.assertIn('Итого: 4 (из них бессрочных: 1)', document.sections[0].total)
        self.assertIn('бессрочно', [row.cells[-1] for row in table.rows])
        self.assertEqual(sum(table.widths), document.text_width)
        self.assertEqual(cooperation_filenames(report), (
            'Договоры_сотрудничество_2025-2026.docx', 'cooperation_contracts_2025-2026.docx',
        ))


class CooperationReportViewTests(TestCase):
    def setUp(self):
        self.editor = make_editor()
        self.contract = make_contract('Договор текущего периода', datetime.date(2026, 1, 1), None)
        self.params = {'submitted': '1', 'year_from': '2026', 'year_to': '2026'}

    def test_access_and_registry(self):
        root = User.objects.create_superuser('root', password='secret')
        for user in (self.editor, root):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(URL).status_code, 200)
                self.assertContains(self.client.get(reverse('reports:report_list')), URL)

        teacher = make_teacher()
        denied = [
            User.objects.create_user('reader', password='secret'),
            make_teacher_user(teacher),
            make_adjunct_user(make_adjunct(teacher)),
            make_student_user(make_student(supervisor=teacher)),
        ]
        for user in denied:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(URL).status_code, 403)
                self.assertEqual(self.client.get(URL, self.params | {'format': 'docx'}).status_code, 403)
                self.assertNotContains(self.client.get(reverse('reports:report_list')), URL)
        self.client.logout()
        self.assertRedirects(self.client.get(URL), f'{reverse("login")}?next={URL}')

    def test_page_default_print_and_validation(self):
        self.client.force_login(self.editor)
        page = self.client.get(URL)
        self.assertContains(page, 'Договоры о научно-техническом сотрудничестве')
        self.assertContains(page, self.contract.title)
        self.assertContains(page, 'бессрочно')
        self.assertContains(page, 'window.print()')
        self.assertContains(page, 'Скачать DOCX')

        page = self.client.get(URL, {'submitted': '1', 'year_from': '2026', 'year_to': '2025'})
        self.assertIsNone(page.context['document'])
        self.assertContains(page, 'не может быть больше')

    def test_empty_period(self):
        self.client.force_login(self.editor)
        page = self.client.get(URL, {'submitted': '1', 'year_from': '2020', 'year_to': '2020'})
        self.assertContains(page, 'Договоры за выбранный период не найдены')
        self.assertContains(page, 'Итого: 0 (из них бессрочных: 0)')

    def test_docx_and_activity_log(self):
        self.client.force_login(self.editor)
        response = self.client.get(URL, self.params | {'format': 'docx'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], DOCX_TYPE)
        disposition = unquote(response['Content-Disposition'])
        self.assertIn('filename="cooperation_contracts_2026.docx"', disposition)
        self.assertIn('Договоры_сотрудничество_2026.docx', disposition)
        text = docx_text(response)
        self.assertIn('Договоры о научно-техническом сотрудничестве', text)
        self.assertIn(self.contract.title, text)
        self.assertIn(self.contract.organization, text)
        self.assertIn(self.contract.subject, text)
        self.assertIn('Итого: 1 (из них бессрочных: 1)', text)
        self.assertTrue(ActivityLog.objects.filter(action=ActivityLog.Action.EXPORT, path=URL).exists())

    def test_query_count_does_not_grow(self):
        self.client.force_login(self.editor)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(URL, self.params).status_code, 200)
            return len(queries)

        few = count()
        for index in range(5):
            make_contract(f'Дополнительный {index}', datetime.date(2026, 2, 1), datetime.date(2026, 12, 1))
        self.assertEqual(count(), few)
