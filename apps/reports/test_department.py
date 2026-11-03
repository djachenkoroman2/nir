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
from apps.publications.models import Publication
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_achievement, make_student, make_teacher_user

from .department import (
    CONTRACTS, DEFENSES, DETAILED, IPS, PEOPLE, PROJECTS, PUBLICATIONS, SECTION_CHOICES, SPECS, STAFF,
    STUDENT_ACHIEVEMENTS, SUMMARY, TALKS, build_department_report,
)
from .docx_common import DOCX_TYPE
from .test_person_reports import docx_text, ip, project, talk
from .tests import publication
from .works import ADJUNCTS, STUDENTS, TEACHERS, Period

URL = reverse('reports:department')
ALL_SECTIONS = [key for key, _ in SECTION_CHOICES]


def metrics(report, key):
    block = next(block for block in report.blocks if block.key == key)
    return {row.label: (row.by_year, row.total) for row in block.metrics}


def people(report, key):
    block = next(block for block in report.people if block.key == key)
    return {row.person.last_name: row.values for row in block.rows}, block.totals


def contract(title, start, end=None):
    return CooperationContract.objects.create(
        title=title, number=title, organization=f'Организация «{title}»', subject=f'Предмет «{title}»',
        start_date=start, end_date=end,
    )


class DepartmentReportBuildTests(TestCase):
    def setUp(self):
        self.first = make_teacher(last_name='Первый')
        self.second = make_teacher(last_name='Второй')
        self.retired = make_teacher(last_name='Ушедший', is_active=False)
        self.student = make_student(last_name='Курсантов', supervisor=self.first)
        self.adjunct = make_adjunct(self.first, last_name='Адъюнктов')
        one, two = {'teacher': self.first}, {'teacher': self.second}
        # Совместная статья двух преподавателей: в итоге кафедры — один раз, в таблице по людям — каждому.
        publication('Совместная', 2025, authors=[one, two, {'external_name': 'Smith J.'}], vak='K1', scopus=True)
        publication('С курсантом', 2026, Publication.Kind.THESES, authors=[one, {'student': self.student}])
        publication('Ушедшего', 2026, authors=[{'teacher': self.retired}], print_sheets='2.5')
        publication('Только внешние', 2025, authors=[{'external_name': 'Внешний В. В.'}])
        publication('Раньше периода', 2024, authors=[one])
        talk('На границе', datetime.date(2025, 12, 31), [one, two])
        talk('Внешний доклад', datetime.date(2025, 6, 1), [{'external_name': 'Гость Г. Г.'}])
        ip('РИД после периода', datetime.date(2027, 1, 1), [one])
        ip('РИД адъюнкта', datetime.date(2026, 1, 1), [{'adjunct': self.adjunct}])
        project('Длинная', datetime.date(2023, 1, 1), leader=self.first)
        project('Закончилась раньше', datetime.date(2020, 1, 1), datetime.date(2024, 12, 31), leader=self.second)
        project('Только 2026', datetime.date(2026, 2, 1), datetime.date(2026, 11, 1), leader=self.second)
        contract('Длинный договор', datetime.date(2024, 1, 1), datetime.date(2026, 6, 1))
        contract('Бессрочный договор', datetime.date(2025, 1, 1))
        contract('Договор только 2026', datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        contract('Договор до периода', datetime.date(2020, 1, 1), datetime.date(2024, 12, 31))
        school = ScientificSchool.objects.create(name='Школа')
        school.leaders.add(self.first)
        DissertationDefense.objects.create(full_name='Защитившийся', kind='candidate', title='Тема',
                                           defense_date=datetime.date(2026, 3, 1), school=school, teacher=self.second)
        make_achievement(self.student, date=datetime.date(2025, 4, 1))
        self.period = Period(2025, 2026)

    def test_summary_metrics_by_year(self):
        report = build_department_report(self.period, SUMMARY)
        publications = metrics(report, PUBLICATIONS)
        self.assertEqual(publications['Публикации — всего'], ([1, 2], 3))
        self.assertEqual(publications['вид: статья'], ([1, 1], 2))
        self.assertEqual(publications['индексация: ВАК, категория: К1'], ([1, 0], 1))
        self.assertEqual(publications['с участием курсантов'], ([0, 1], 1))
        self.assertEqual(publications['объём, п. л. (сумма, где указан)'], ([0, '2,5'], '2,5'))
        self.assertEqual(metrics(report, TALKS)['Доклады — всего'], ([1, 0], 1))
        self.assertEqual(metrics(report, IPS)['РИД — всего'], ([0, 1], 1))
        # НИОКР считается в каждом году, когда велась, а за период — один раз.
        self.assertEqual(metrics(report, PROJECTS)['НИОКР — всего (выполнялись в периоде)'], ([1, 2], 2))
        self.assertEqual(metrics(report, CONTRACTS)['Договоры — всего'], ([2, 3], 3))
        self.assertEqual(metrics(report, CONTRACTS)['Из них бессрочные'], ([1, 1], 1))
        self.assertEqual(metrics(report, DEFENSES)['Защиты диссертаций — всего'], ([0, 1], 1))
        self.assertEqual(metrics(report, STUDENT_ACHIEVEMENTS)['Достижения курсантов — всего'], ([1, 0], 1))
        staff = {label: value for label, value, _ in report.staff}
        self.assertEqual(staff['Преподаватели (работают на кафедре) — всего'], 2)

    def test_single_year_has_no_year_columns_and_boundaries(self):
        report = build_department_report(Period(2025, 2025), SUMMARY)
        self.assertFalse(report.by_year)
        self.assertEqual(metrics(report, PUBLICATIONS)['Публикации — всего'], ([], 1))
        self.assertEqual(metrics(report, TALKS)['Доклады — всего'], ([], 1))  # 31.12.2025 — в периоде
        self.assertEqual(metrics(report, IPS)['РИД — всего'], ([], 0))  # 01.01.2026 — уже нет

    def test_people_table_counts_each_author(self):
        report = build_department_report(self.period, SUMMARY)
        rows, totals = people(report, TEACHERS)
        self.assertEqual(rows['Первый'][:2], [2, 1])  # публикаций, из них ВАК
        self.assertEqual(rows['Второй'][:2], [1, 1])
        self.assertNotIn('Ушедший', rows)  # по умолчанию — без неработающих
        self.assertEqual(totals[0], 3)  # без повторов, с публикацией ушедшего
        self.assertEqual(rows['Первый'][6], 1)  # НИОКР
        self.assertIsNone(rows['Первый'][7])  # достижений у преподавателей нет
        self.assertEqual(report.people_totals[0], 3)
        self.assertEqual(report.people_totals[6], 2)
        self.assertEqual(report.people_totals[7], 1)
        rows, _ = people(build_department_report(self.period, SUMMARY, include_inactive=True), TEACHERS)
        self.assertEqual(rows['Ушедший'][0], 1)

    def test_categories_filter(self):
        report = build_department_report(self.period, SUMMARY, categories=[STUDENTS])
        self.assertEqual(metrics(report, PUBLICATIONS)['Публикации — всего'][1], 1)  # только «С курсантом»
        self.assertEqual(metrics(report, TALKS)['Доклады — всего'][1], 0)
        self.assertEqual([block.key for block in report.people], [STUDENTS])
        self.assertNotIn('Достижения адъюнктов', [block.title for block in report.blocks])
        staff = [label for label, _, _ in report.staff]
        self.assertEqual(staff[0], 'Курсанты, занимающиеся НИР (обучаются) — всего')
        # НИОКР, договоры и защиты — показатели кафедры в целом.
        self.assertEqual(metrics(report, PROJECTS)['НИОКР — всего (выполнялись в периоде)'][1], 2)
        self.assertEqual(metrics(report, CONTRACTS)['Договоры — всего'][1], 3)

    def test_sections_filter(self):
        report = build_department_report(self.period, SUMMARY, sections=[TALKS, PEOPLE])
        self.assertEqual([block.key for block in report.blocks], [TALKS])
        self.assertIsNone(report.staff)
        self.assertIsNone(report.schools)
        self.assertIsNotNone(report.people)

    def test_detailed_totals_match_summary(self):
        for categories in ([TEACHERS, ADJUNCTS, STUDENTS], [STUDENTS], [ADJUNCTS]):
            summary = build_department_report(self.period, SUMMARY, categories=categories)
            detailed = build_department_report(self.period, DETAILED, categories=categories)
            self.assertEqual(len(summary.blocks), len(detailed.blocks))
            for one, other in zip(summary.blocks, detailed.blocks):
                with self.subTest(categories=categories, section=one.key):
                    self.assertEqual(one.total, len(other.entries))
            self.assertEqual(sum(value for _, value, is_total in summary.staff if is_total),
                             sum(len(lines) for _, lines in detailed.staff_people))

    def test_detailed_entries(self):
        report = build_department_report(self.period, DETAILED)
        publications = next(block for block in report.blocks if block.key == PUBLICATIONS).entries
        text = [str(entry) for entry in publications]
        self.assertTrue(text[0].startswith('Первый И. И., Второй И. И., Smith J. Совместная (статья) // Журнал'))
        self.assertNotIn('Только внешние', ' '.join(text))
        # Люди кафедры выделены полужирным, внешние — нет.
        self.assertIn(('Первый И. И.', True), publications[0].parts)
        self.assertIn(('Smith J.', False), publications[0].parts)
        contracts = next(block for block in report.blocks if block.key == CONTRACTS).entries
        contract_text = ' '.join(map(str, contracts))
        self.assertIn('Бессрочный договор', contract_text)
        self.assertIn('Организация «Бессрочный договор»', contract_text)
        self.assertIn('бессрочно', contract_text)
        self.assertNotIn('Договор до периода', contract_text)
        self.assertIsNone(report.people)


class DepartmentReportViewTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Первый')
        publication('Статья', 2025, authors=[{'teacher': self.teacher}])
        contract('Договор', datetime.date(2025, 1, 1))
        self.editor = make_editor()

    def params(self, **extra):
        return {'submitted': '1', 'view': SUMMARY, 'year_from': '2024', 'year_to': '2025',
                'sections': ALL_SECTIONS, **extra}

    def test_access(self):
        root = User.objects.create_superuser('root', password='secret')
        for user in (self.editor, root):
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(URL).status_code, 200)
                self.assertContains(self.client.get(reverse('reports:report_list')), URL)
        student = make_student(supervisor=self.teacher)
        denied = [make_teacher_user(self.teacher), make_adjunct_user(make_adjunct(self.teacher)),
                  make_student_user(student), User.objects.create_user('reader')]
        for user in denied:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(self.client.get(URL).status_code, 403)
                self.assertEqual(self.client.get(URL, self.params(format='docx')).status_code, 403)
                self.assertNotContains(self.client.get(reverse('reports:report_list')), URL)
        self.client.logout()
        self.assertRedirects(self.client.get(URL), f'{reverse("login")}?next={URL}')

    def test_page_and_validation(self):
        self.client.force_login(self.editor)
        page = self.client.get(URL, self.params())
        self.assertContains(page, 'Отчёт о научно-исследовательской работе кафедры')
        self.assertContains(page, 'Показатели по людям')
        self.assertContains(page, 'сумма строк может быть больше итога')
        page = self.client.get(URL, self.params(view=DETAILED))
        self.assertContains(page, 'Итого: 1')
        titles = [section.title for section in page.context['document'].sections]
        self.assertFalse(any('Показатели по людям' in title for title in titles))  # только в консолидированном
        page = self.client.get(URL, self.params(sections=[]))
        self.assertIsNone(page.context['document'])
        self.assertContains(page, 'Выберите хотя бы один раздел')
        page = self.client.get(URL, self.params(year_from='2026', year_to='2025'))
        self.assertContains(page, 'не может быть больше')

    def test_docx_both_views(self):
        self.client.force_login(self.editor)
        for view, kind, fallback in ((SUMMARY, 'сводный', 'summary'), (DETAILED, 'подробный', 'detailed')):
            with self.subTest(view=view):
                response = self.client.get(URL, self.params(view=view, format='docx'))
                self.assertEqual(response['Content-Type'], DOCX_TYPE)
                disposition = unquote(response['Content-Disposition'])
                self.assertIn(f'filename="department_{fallback}_2024-2025.docx"', disposition)
                self.assertIn(f'НИР_кафедры_{kind}_2024-2025.docx', disposition)
                text = docx_text(response)
                self.assertIn('Отчёт о научно-исследовательской работе кафедры', text)
                self.assertIn('Публикации — всего' if view == SUMMARY else 'Статья (статья)', text)
                self.assertIn('Договоры — всего' if view == SUMMARY else 'Предмет «Договор»', text)
                self.assertIn('Заведующий кафедрой', text)
        self.assertEqual(ActivityLog.objects.filter(action=ActivityLog.Action.EXPORT, path=URL).count(), 2)

    def test_query_count_does_not_grow(self):
        self.client.force_login(self.editor)

        def count(view):
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(URL, self.params(view=view)).status_code, 200)
            return len(queries)

        colleague = make_teacher(last_name='Второй')

        def add(index):
            student = make_student(last_name=f'Курсант{index}', supervisor=colleague)
            make_achievement(student, date=datetime.date(2025, 1, 1))
            publication(f'Статья {index}', 2024, authors=[{'teacher': colleague}, {'student': student}])
            talk(f'Доклад {index}', datetime.date(2025, 1, 1), [{'teacher': self.teacher}, {'student': student}])
            ip(f'РИД {index}', datetime.date(2024, 5, 1), [{'teacher': colleague}])
            project(f'НИОКР {index}', datetime.date(2024, 1, 1), leader=colleague)
            contract(f'Договор {index}', datetime.date(2024, 1, 1))

        add(0)  # по записи каждого вида: подгрузка авторов и участников выполняется, только если записи есть
        few = {view: count(view) for view in (SUMMARY, DETAILED)}
        for index in range(1, 5):
            add(index)
        self.assertEqual({view: count(view) for view in (SUMMARY, DETAILED)}, few)


class SpecsTests(TestCase):
    def test_every_section_has_a_title(self):
        keys = {key for key, _ in SECTION_CHOICES}
        self.assertTrue({spec.key for spec in SPECS} <= keys)
        self.assertIn(STAFF, keys)
