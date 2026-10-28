import datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import unquote

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from docx import Document

from apps.adjuncts.tests import make_adjunct, make_adjunct_user
from apps.conferences.models import Conference, Report
from apps.core.cabinet import RULES
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.publications.models import Publication, PublicationAuthor
from apps.staff.tests import make_editor, make_teacher
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_student, make_teacher_user

from .form16 import IP, SCIENCE, STUDY, build_form16, volume
from .views import DOCX_TYPE

NBSP = ' '


def publication(title, year=2024, kind=Publication.Kind.ARTICLE, authors=(), **fields):
    record = Publication.objects.create(title=title, year=year, kind=kind, source='Журнал', **fields)
    for order, author in enumerate(authors, start=1):
        PublicationAuthor.objects.create(publication=record, order=order, **author)
    return record


def form16_url(person):
    return reverse('reports:form16', args=[person._meta.model_name, person.pk])


def titles(report):
    return {section.key: [row.title for row in section.rows] for section in report.sections}


class Form16BuildTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Петров', first_name='Пётр', middle_name='Петрович')
        self.colleague = make_teacher(last_name='Коллегин', first_name='Олег', middle_name='Ильич')
        me, colleague = {'teacher': self.teacher}, {'teacher': self.colleague}
        publication('Б-статья', 2023, authors=[me, colleague, {'external_name': 'Smith J.'}])
        publication('А-статья', 2023, authors=[me])
        publication('Ранние тезисы', 2020, Publication.Kind.THESES, authors=[colleague, me])
        publication('Пособие', 2022, Publication.Kind.STUDY_GUIDE, authors=[me], print_sheets=Decimal('6.50'))
        publication('Чужая статья', 2023, authors=[colleague])
        ip = IntellectualProperty.objects.create(
            title='Программа', kind=IntellectualProperty.Kind.SOFTWARE, number='2024610001',
            registration_date=datetime.date(2024, 3, 1), holder='Университет',
        )
        IntellectualPropertyAuthor.objects.create(intellectual_property=ip, teacher=self.teacher, order=1)

    def test_sections_numbering_and_order(self):
        report = build_form16(self.teacher)
        self.assertEqual(titles(report), {
            SCIENCE: ['Ранние тезисы (тезисы доклада)', 'А-статья (статья)', 'Б-статья (статья)'],
            STUDY: ['Пособие (учебное пособие)'],
            IP: ['Программа (свидетельство на программу для ЭВМ)'],
        })
        numbers = [row.number for section in report.sections for row in section.rows]
        self.assertEqual(numbers, [1, 2, 3, 4, 5])
        self.assertEqual([section.number for section in report.sections], [1, 2, 3])

    def test_period_and_sections_filters(self):
        report = build_form16(self.teacher, year_from=2022, year_to=2023, sections=[SCIENCE, STUDY])
        self.assertEqual(titles(report), {SCIENCE: ['А-статья (статья)', 'Б-статья (статья)'],
                                          STUDY: ['Пособие (учебное пособие)']})
        self.assertEqual(report.period, '2022–2023 гг.')
        self.assertEqual(titles(build_form16(self.teacher, year_from=2025))[IP], [])

    def test_coauthors_work_form_and_imprint(self):
        rows = {row.title: row for section in build_form16(self.teacher).sections for row in section.rows}
        self.assertEqual(rows['Б-статья (статья)'].coauthors, 'Коллегин О. И., Smith J.')
        self.assertEqual(rows['А-статья (статья)'].coauthors, '—')
        self.assertEqual(rows['А-статья (статья)'].work_form, 'печатная')
        program = rows['Программа (свидетельство на программу для ЭВМ)']
        self.assertEqual(program.work_form, 'электронная')
        self.assertIn('Свидетельство № 2024610001, дата регистрации 01.03.2024', program.imprint)
        self.assertEqual(program.coauthors, '—')

    def test_volume(self):
        cases = [
            ({'print_sheets': Decimal('6.50')}, f'6,5{NBSP}п.{NBSP}л.'),
            ({'print_sheets': Decimal('3.00')}, f'3{NBSP}п.{NBSP}л.'),
            ({'pages': '15–28'}, f'14{NBSP}с.'),
            ({'pages': 'С. 5-5'}, f'1{NBSP}с.'),
            ({'pages': '240 с.'}, '240 с.'),
            ({}, '—'),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                self.assertEqual(volume(Publication(title='Т', year=2024, **fields)), expected)

    def test_report_without_theses_is_not_included(self):
        conference = Conference.objects.create(title='Конференция', level='national', start_date='2024-05-01')
        Report.objects.create(conference=conference, title='Доклад без тезисов')
        theses = publication('Тезисы доклада', 2024, Publication.Kind.THESES, authors=[{'teacher': self.teacher}])
        Report.objects.create(conference=conference, title='Доклад с тезисами', publication=theses)
        science = titles(build_form16(self.teacher))[SCIENCE]
        self.assertIn('Тезисы доклада (тезисы доклада)', science)
        self.assertFalse(any('Доклад' in title for title in science))

    def test_heading(self):
        report = build_form16(self.teacher)
        self.assertEqual(report.signature, 'П. П. Петров')
        self.assertIn('доцент', report.position)
        student = make_student(group='ИБ-31')
        self.assertEqual(build_form16(student).position, 'курсант, учебная группа ИБ-31')
        self.assertTrue(build_form16(student).is_empty)


class Form16AccessTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Руководителев')
        self.other_teacher = make_teacher(last_name='Чужой')
        self.student = make_student(supervisor=self.teacher)
        self.adjunct = make_adjunct(self.teacher)
        publication('Статья курсанта', authors=[{'student': self.student}, {'teacher': self.teacher}])

    def status(self, url):
        return self.client.get(url).status_code

    def test_each_role_gets_own_report(self):
        for user, person in [
            (make_teacher_user(self.teacher), self.teacher),
            (make_adjunct_user(self.adjunct), self.adjunct),
            (make_student_user(self.student), self.student),
        ]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertRedirects(self.client.get(reverse('reports:form16_own')), form16_url(person))
                self.assertEqual(self.status(form16_url(person)), 200)
                self.assertContains(self.client.get(reverse('reports:report_list')), 'Форма № 16')

    def test_supervisor_sees_supervisees_but_not_others(self):
        self.client.force_login(make_teacher_user(self.teacher))
        self.assertEqual(self.status(form16_url(self.student)), 200)
        self.assertEqual(self.status(form16_url(self.adjunct)), 200)
        self.assertEqual(self.status(form16_url(self.other_teacher)), 404)
        response = self.client.get(self.student.get_absolute_url())
        self.assertContains(response, form16_url(self.student))

    def test_other_people_get_404(self):
        foreign_student = make_student(last_name='Сосед', supervisor=self.other_teacher)
        cases = [
            (make_teacher_user(self.other_teacher, 'other'), [self.student, self.adjunct, self.teacher]),
            (make_adjunct_user(self.adjunct), [self.teacher, self.student]),
            (make_student_user(foreign_student), [self.student, self.adjunct, self.teacher]),
        ]
        for user, targets in cases:
            self.client.force_login(user)
            for target in targets:
                with self.subTest(user=user.username, target=target):
                    self.assertEqual(self.status(form16_url(target)), 404)

    def test_same_pk_people_are_not_confused(self):
        teacher = make_teacher(pk=900, last_name='Однофамильцев')
        adjunct = make_adjunct(self.teacher, pk=900, last_name='Другой')
        self.client.force_login(make_teacher_user(teacher, 'same_pk'))
        self.assertEqual(self.status(reverse('reports:form16', args=['teacher', 900])), 200)
        self.assertEqual(self.status(reverse('reports:form16', args=['adjunct', 900])), 404)
        self.assertEqual(self.status(reverse('reports:form16', args=['unknown', 900])), 404)
        self.assertEqual(adjunct.pk, teacher.pk)

    def test_editor_chooses_anyone(self):
        self.client.force_login(make_editor())
        self.assertEqual(self.status(reverse('reports:form16_own')), 200)
        response = self.client.get(reverse('reports:form16_own'), {
            'submitted': '1', 'person': f'student-{self.student.pk}', 'sections': [SCIENCE], 'year_from': '2020',
        })
        self.assertRedirects(response, form16_url(self.student) + '?submitted=1&sections=science&year_from=2020',
                             fetch_redirect_response=False)
        page = self.client.get(form16_url(self.other_teacher))
        self.assertEqual(page.status_code, 200)
        self.assertIn('person', page.context['form'].fields)

    def test_reports_are_in_role_whitelists(self):
        for role, rules in RULES.items():
            with self.subTest(role=role):
                self.assertTrue({'reports:report_list', 'reports:form16_own', 'reports:form16'} <= set(rules))

    def test_header_has_reports_item(self):
        self.client.force_login(make_teacher_user(self.teacher))
        response = self.client.get(self.teacher.get_absolute_url())
        self.assertContains(response, f'href="{reverse("reports:report_list")}"')

    def test_invalid_parameters(self):
        self.client.force_login(make_teacher_user(self.teacher))
        response = self.client.get(form16_url(self.teacher), {'submitted': '1', 'year_from': '2025', 'year_to': '2020',
                                                              'sections': [SCIENCE]})
        self.assertIsNone(response.context['report'])
        self.assertContains(response, 'не может быть больше')
        response = self.client.get(form16_url(self.teacher), {'submitted': '1'})
        self.assertContains(response, 'Выберите хотя бы один раздел')


class Form16DocxTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher(last_name='Петров', first_name='Пётр', middle_name='Петрович')
        publication('Новая статья', 2024, authors=[{'teacher': self.teacher}])
        publication('Старая статья', 2015, authors=[{'teacher': self.teacher}])
        self.client.force_login(make_teacher_user(self.teacher))

    def download(self, **params):
        return self.client.get(form16_url(self.teacher), {'format': 'docx', **params})

    def table_text(self, response):
        document = Document(BytesIO(response.content))
        return [[cell.text for cell in row.cells] for row in document.tables[0].rows]

    def test_docx_response_and_content(self):
        response = self.download()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], DOCX_TYPE)
        disposition = response['Content-Disposition']
        self.assertIn(f'filename="form16_teacher_{self.teacher.pk}.docx"', disposition)
        self.assertIn('Форма_16_Петров_П_П.docx', unquote(disposition))
        rows = self.table_text(response)
        self.assertEqual(rows[0][1], 'Наименование работы, её вид')
        flat = [cell for row in rows for cell in row]
        self.assertIn('Старая статья (статья)', flat)
        self.assertIn('1. Научные труды', flat)
        self.assertIn('нет', flat)  # пустые разделы

    def test_docx_uses_period(self):
        flat = [cell for row in self.table_text(self.download(submitted='1', year_from='2020', sections=[SCIENCE]))
                for cell in row]
        self.assertIn('Новая статья (статья)', flat)
        self.assertNotIn('Старая статья (статья)', flat)
        self.assertNotIn('3. Объекты интеллектуальной собственности', flat)

    def test_page_has_buttons_and_print(self):
        response = self.client.get(form16_url(self.teacher))
        self.assertContains(response, 'Скачать DOCX')
        self.assertContains(response, 'window.print()')
        self.assertContains(response, 'доклады без опубликованных тезисов не включаются')

    def test_no_queries_per_row(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(form16_url(self.teacher)).status_code, 200)
            return len(queries)

        few = count()
        colleague = make_teacher(last_name='Соавторов')
        for index in range(6):
            publication(f'Статья {index}', authors=[{'teacher': self.teacher}, {'teacher': colleague},
                                                    {'external_name': 'Внешний В. В.'}])
        self.assertEqual(count(), few)
