import datetime
from io import BytesIO
from urllib.parse import unquote

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from docx import Document

from apps.accounts.models import User
from apps.activity.models import ActivityLog
from apps.adjuncts.models import AdjunctAchievement, PlanStage
from apps.adjuncts.tests import make_adjunct, make_adjunct_user, make_student_task, make_task
from apps.conferences.models import Conference, Report, ReportSpeaker
from apps.core.cabinet import ADJUNCT, RULES, STUDENT, TEACHER
from apps.ip.models import IntellectualProperty, IntellectualPropertyAuthor
from apps.research.models import Participant, ResearchProject
from apps.schools.models import DissertationDefense, ScientificSchool
from apps.staff.tests import make_editor, make_teacher
from apps.students.models import Student
from apps.students.test_cabinet import make_student_user
from apps.students.tests import make_achievement, make_student, make_teacher_user

from .access import person_report_url
from .docx_common import DOCX_TYPE
from .plan import build_plan_report
from .supervision import build_supervision_report
from .tests import publication
from .work import build_work_report
from .works import Period

TODAY = timezone.localdate()
P2025 = Period(2025, 2026)


def talk(title, start, speakers, level=Conference.Level.NATIONAL):
    conference = Conference.objects.create(title=f'Конференция «{title}»', level=level, start_date=start)
    report = Report.objects.create(conference=conference, title=title)
    for order, speaker in enumerate(speakers, start=1):
        ReportSpeaker.objects.create(report=report, order=order, **speaker)
    return report


def ip(title, registered, authors, kind=IntellectualProperty.Kind.SOFTWARE):
    record = IntellectualProperty.objects.create(title=title, kind=kind, number=title, registration_date=registered)
    for order, author in enumerate(authors, start=1):
        IntellectualPropertyAuthor.objects.create(intellectual_property=record, order=order, **author)
    return record


def project(title, start, end=None, leader=None, status=ResearchProject.Status.IN_PROGRESS):
    record = ResearchProject.objects.create(title=title, start_date=start, end_date=end, status=status)
    if leader:
        Participant.objects.create(project=record, teacher=leader, role=Participant.Role.LEADER)
    return record


def docx_text(response):
    document = Document(BytesIO(response.content))
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return '\n'.join([p.text for p in document.paragraphs] + cells)


class PeopleMixin:
    """Преподаватель с подопечными курсантом и адъюнктом, другой преподаватель и его курсант."""

    def make_people(self):
        self.teacher = make_teacher(last_name='Руководителев', first_name='Сергей', middle_name='Петрович')
        self.other_teacher = make_teacher(last_name='Чужой')
        self.student = make_student(last_name='Курсантов', supervisor=self.teacher)
        self.adjunct = make_adjunct(self.teacher, last_name='Адъюнктов')
        self.other_student = make_student(last_name='Сосед', supervisor=self.other_teacher)


class WorkReportBuildTests(PeopleMixin, TestCase):
    def setUp(self):
        self.make_people()
        me, student = {'teacher': self.teacher}, {'student': self.student}
        publication('Совместная статья', 2025, authors=[me, student])
        publication('Статья ВАК', 2026, authors=[me], vak='K1', scopus=True)
        publication('Старая статья', 2020, authors=[me, student])
        talk('Доклад', datetime.date(2025, 5, 20), [me, student])
        talk('Старый доклад', datetime.date(2024, 12, 31), [me])
        ip('Программа', datetime.date(2026, 1, 1), [{'adjunct': self.adjunct}])
        make_achievement(self.student, date=datetime.date(2025, 3, 1))
        make_achievement(self.student, title='Старое', date=datetime.date(2024, 3, 1))
        project('Текущая НИОКР', datetime.date(2024, 1, 1), leader=self.teacher)
        project('Закрытая НИОКР', datetime.date(2020, 1, 1), datetime.date(2024, 12, 31), leader=self.teacher)
        school = ScientificSchool.objects.create(name='Школа')
        school.leaders.add(self.teacher)
        DissertationDefense.objects.create(full_name='Защитившийся', kind='candidate', title='Тема',
                                           defense_date=datetime.date(2025, 6, 1), school=school,
                                           supervisor=self.teacher)

    def test_teacher_report_by_period(self):
        report = build_work_report(self.teacher, P2025)
        self.assertEqual([p.title for p in report.publications], ['Совместная статья', 'Статья ВАК'])
        self.assertEqual([t.title for t in report.talks], ['Доклад'])
        self.assertEqual([m.project.title for m in report.memberships], ['Текущая НИОКР'])
        self.assertEqual([d.full_name for d in report.defenses], ['Защитившийся'])
        self.assertEqual([s.name for s in report.schools], ['Школа'])
        totals = dict(report.totals())
        self.assertEqual(totals['Публикации — всего'], 2)
        self.assertEqual(totals['из них ВАК'], 1)
        self.assertEqual(totals['из них Scopus'], 1)
        self.assertEqual(totals['Участие в НИОКР'], 1)

    def test_student_and_adjunct_reports(self):
        report = build_work_report(self.student, P2025)
        self.assertEqual([p.title for p in report.publications], ['Совместная статья'])
        self.assertEqual([t.title for t in report.talks], ['Доклад'])
        self.assertEqual([a.date.year for a in report.achievements], [2025])
        self.assertEqual(dict(report.totals())['Достижения — всего'], 1)
        report = build_work_report(self.adjunct, P2025)
        self.assertEqual([i.title for i in report.intellectual_properties], ['Программа'])
        self.assertEqual(build_work_report(self.adjunct, Period(2025, 2025)).intellectual_properties, [])

    def test_page_and_docx(self):
        self.client.force_login(make_teacher_user(self.teacher))
        url = person_report_url('work', self.teacher)
        page = self.client.get(url, {'submitted': '1', 'year_from': '2025', 'year_to': '2026'})
        self.assertContains(page, 'Отчёт о научной работе преподавателя')
        self.assertContains(page, 'Совместная статья')
        self.assertContains(page, 'Курсантов П. И.')  # соавтор
        self.assertNotContains(page, 'Старая статья')
        self.assertContains(page, 'Скачать DOCX')
        self.assertContains(page, 'window.print()')
        response = self.client.get(url, {'submitted': '1', 'year_from': '2025', 'year_to': '2026', 'format': 'docx'})
        self.assertEqual(response['Content-Type'], DOCX_TYPE)
        disposition = unquote(response['Content-Disposition'])
        self.assertIn(f'filename="work_teacher_{self.teacher.pk}_2025-2026.docx"', disposition)
        self.assertIn('Научная_работа_Руководителев_С_П_2025-2026.docx', disposition)
        text = docx_text(response)
        self.assertIn('Совместная статья (статья)', text)
        self.assertIn('Текущая НИОКР', text)
        self.assertIn('Преподаватель  _______________  С. П. Руководителев', text)
        self.assertTrue(ActivityLog.objects.filter(action=ActivityLog.Action.EXPORT, path=url).exists())

    def test_default_period_is_current_year_and_invalid_period(self):
        self.client.force_login(make_teacher_user(self.teacher))
        url = person_report_url('work', self.teacher)
        self.assertContains(self.client.get(url), f'Период: {TODAY.year} г.')
        response = self.client.get(url, {'submitted': '1', 'year_from': '2026', 'year_to': '2025'})
        self.assertIsNone(response.context['document'])
        self.assertContains(response, 'не может быть больше')

    def test_no_queries_per_record(self):
        self.client.force_login(make_teacher_user(self.teacher))
        url = person_report_url('work', self.teacher)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.client.get(url, {'submitted': '1', 'year_from': '2020', 'year_to': '2026'})
            return len(queries)

        few = count()
        for index in range(5):
            publication(f'Ещё {index}', 2025, authors=[{'teacher': self.teacher}, {'teacher': self.other_teacher}])
            talk(f'Ещё доклад {index}', datetime.date(2025, 1, 1), [{'teacher': self.teacher}])
        self.assertEqual(count(), few)


class PlanReportTests(PeopleMixin, TestCase):
    def setUp(self):
        self.make_people()
        S = PlanStage.Status
        past, future = TODAY - datetime.timedelta(days=10), TODAY + datetime.timedelta(days=10)
        for year, title, status, due in [
            (1, 'Экзамен', S.DONE, past), (1, 'Статья', S.PLANNED, past), (2, 'Глава', S.IN_PROGRESS, future),
            (2, 'Доклад', S.FAILED, past),
        ]:
            PlanStage.objects.create(adjunct=self.adjunct, study_year=year, title=title, kind='other',
                                     due_date=due, status=status, supervisor_note='Отметка' if title == 'Экзамен' else '')

    def test_counts_and_study_year(self):
        report = build_plan_report(self.adjunct)
        self.assertEqual(report.counts, {'total': 4, 'done': 1, 'in_progress': 1, 'planned': 1, 'failed': 1,
                                         'overdue': 1})
        self.assertEqual([stage.title for stage in build_plan_report(self.adjunct, 2).stages], ['Доклад', 'Глава'])  # по сроку

    def test_page_and_docx(self):
        self.client.force_login(make_adjunct_user(self.adjunct))
        url = person_report_url('plan', self.adjunct)
        page = self.client.get(url)
        self.assertContains(page, 'запланирован (просрочен)')
        self.assertContains(page, '1-й год обучения')
        response = self.client.get(url, {'submitted': '1', 'study_year': '2', 'format': 'docx'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'filename="plan_adjunct_{self.adjunct.pk}_2.docx"', response['Content-Disposition'])
        text = docx_text(response)
        self.assertIn('Глава', text)
        self.assertNotIn('Экзамен', text)
        self.assertIn('Научный руководитель  _______________  С. П. Руководителев', text)


class SupervisionReportTests(PeopleMixin, TestCase):
    def setUp(self):
        self.make_people()
        self.graduate = make_student(last_name='Выпускник', supervisor=self.teacher, status=Student.Status.GRADUATED)
        publication('Статья курсанта', 2026, authors=[{'student': self.student}, {'teacher': self.teacher}])
        publication('Старая статья курсанта', 2020, authors=[{'student': self.student}])
        AdjunctAchievement.objects.create(adjunct=self.adjunct, kind='grant', level='national', title='Грант',
                                          result='победитель', date=datetime.date(2026, 2, 1))
        make_student_task(self.student, due_date=TODAY - datetime.timedelta(days=1))
        make_student_task(self.student, status='done')
        make_task(self.adjunct)
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Этап', kind='other',
                                 due_date=TODAY - datetime.timedelta(days=1))
        PlanStage.objects.create(adjunct=self.adjunct, study_year=1, title='Готово', kind='other',
                                 due_date=TODAY, status=PlanStage.Status.DONE)

    def test_rows_and_totals(self):
        report = build_supervision_report(self.teacher, Period(2026, 2026))
        self.assertEqual([row.person for row in report.students], [self.student])
        # публикаций, докладов, РИД, достижений, открытых задач, просроченных задач
        self.assertEqual(report.students[0].values, [1, 0, 0, 0, 1, 1])
        self.assertEqual(report.adjuncts[0].values, [0, 0, 0, 1, 1, 0])
        self.assertEqual(report.adjuncts[0].plan, 'выполнено 1 из 2, просрочено 1')
        self.assertEqual(report.totals(report.students + report.adjuncts), [1, 0, 0, 1, 2, 1])
        report = build_supervision_report(self.teacher, Period(2020, 2026), include_finished=True)
        self.assertIn(self.graduate, [row.person for row in report.students])
        self.assertEqual(report.students[[r.person for r in report.students].index(self.student)].values[0], 2)

    def test_query_count_does_not_grow(self):
        self.client.force_login(make_teacher_user(self.teacher))
        url = person_report_url('supervision', self.teacher)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(url).status_code, 200)
            return len(queries)

        few = count()
        for index in range(4):
            student = make_student(last_name=f'Новый{index}', supervisor=self.teacher)
            make_student_task(student)
            make_adjunct(self.teacher, last_name=f'Новый{index}')
        self.assertEqual(count(), few)

    def test_docx(self):
        self.client.force_login(make_teacher_user(self.teacher))
        response = self.client.get(person_report_url('supervision', self.teacher), {'format': 'docx'})
        self.assertIn(f'filename="supervision_teacher_{self.teacher.pk}_{TODAY.year}.docx"',
                      response['Content-Disposition'])
        text = docx_text(response)
        self.assertIn('Курсантов Пётр Ильич', text)
        self.assertIn('Итого: адъюнкты (1)', text)
        self.assertNotIn('Выпускник', text)


class PersonReportAccessTests(PeopleMixin, TestCase):
    """Матрица доступа: сам, руководитель, редактор — 200; чужие — 404; страницы вне кабинета — 403."""

    def setUp(self):
        self.make_people()
        self.root = User.objects.create_superuser('root', password='secret')
        self.editor = make_editor()
        self.teacher_user = make_teacher_user(self.teacher)
        self.other_teacher_user = make_teacher_user(self.other_teacher, 'other')
        self.adjunct_user = make_adjunct_user(self.adjunct)
        self.student_user = make_student_user(self.student)
        self.other_student_user = make_student_user(self.other_student, 'neighbour')
        self.reader = User.objects.create_user('reader', password='secret')

    def status(self, user, url):
        self.client.force_login(user)
        return self.client.get(url).status_code

    def check(self, url, allowed, denied, denied_status=404):
        for user in allowed:
            with self.subTest(url=url, user=user.username):
                self.assertEqual(self.status(user, url), 200)
        for user in denied:
            with self.subTest(url=url, user=user.username):
                self.assertEqual(self.status(user, url), denied_status)
        self.client.logout()
        self.assertRedirects(self.client.get(url), f'{reverse("login")}?next={url}')

    def test_work_report_and_card(self):
        for name in ('work', 'card'):
            self.check(person_report_url(name, self.student),
                       [self.root, self.editor, self.teacher_user, self.student_user],
                       [self.other_teacher_user, self.adjunct_user, self.other_student_user, self.reader])
            self.check(person_report_url(name, self.adjunct),
                       [self.root, self.editor, self.teacher_user, self.adjunct_user],
                       [self.other_teacher_user, self.student_user, self.reader])
            self.check(person_report_url(name, self.teacher), [self.root, self.editor, self.teacher_user],
                       [self.other_teacher_user, self.adjunct_user, self.student_user, self.reader])

    def test_plan_report(self):
        self.check(person_report_url('plan', self.adjunct),
                   [self.root, self.editor, self.teacher_user, self.adjunct_user],
                   [self.other_teacher_user, self.student_user, self.reader])
        # Нет такого адъюнкта — 404.
        self.assertEqual(self.status(self.editor, reverse('reports:plan', args=[self.student.pk + 1000])), 404)
        for user in (self.student_user, self.teacher_user, self.reader):
            with self.subTest(user=user.username):
                self.assertEqual(self.status(user, reverse('reports:plan_own')), 404)

    def test_supervision_report(self):
        self.check(person_report_url('supervision', self.teacher), [self.root, self.editor, self.teacher_user],
                   [self.other_teacher_user, self.adjunct_user, self.student_user, self.reader])
        for user in (self.adjunct_user, self.student_user, self.reader):
            with self.subTest(user=user.username):
                self.assertEqual(self.status(user, reverse('reports:supervision_own')), 404)

    def test_own_urls_redirect_and_editor_chooses(self):
        cases = [
            (self.teacher_user, 'work_own', 'work', self.teacher),
            (self.student_user, 'work_own', 'work', self.student),
            (self.adjunct_user, 'plan_own', 'plan', self.adjunct),
            (self.teacher_user, 'supervision_own', 'supervision', self.teacher),
        ]
        for user, own, name, person in cases:
            with self.subTest(user=user.username, url=own):
                self.client.force_login(user)
                self.assertRedirects(self.client.get(reverse(f'reports:{own}')), person_report_url(name, person))
        self.client.force_login(self.editor)
        page = self.client.get(reverse('reports:plan_own'))
        self.assertContains(page, 'Выберите человека')
        self.assertIn(f'adjunct-{self.adjunct.pk}', dict(page.context['form'].fields['person'].choices))
        self.assertNotIn(f'student-{self.student.pk}', dict(page.context['form'].fields['person'].choices))
        response = self.client.get(reverse('reports:work_own'), {'submitted': '1', 'person': f'student-{self.student.pk}',
                                                                 'year_from': '2025', 'year_to': '2026'})
        self.assertRedirects(response, person_report_url('work', self.student) + '?submitted=1&year_from=2025'
                             '&year_to=2026', fetch_redirect_response=False)

    def test_supervisor_switches_between_supervisees(self):
        self.client.force_login(self.teacher_user)
        page = self.client.get(person_report_url('work', self.student))
        choices = dict(page.context['form'].fields['person'].choices)
        self.assertEqual(set(choices), {f'teacher-{self.teacher.pk}', f'student-{self.student.pk}',
                                        f'adjunct-{self.adjunct.pk}'})

    def test_reports_are_in_role_whitelists(self):
        names = {'reports:work_own', 'reports:work', 'reports:plan_own', 'reports:plan', 'reports:supervision_own',
                 'reports:supervision', 'reports:card', 'reports:account'}
        for role in (TEACHER, ADJUNCT, STUDENT):
            with self.subTest(role=role):
                self.assertTrue(names <= set(RULES[role]))
                self.assertIn('core:profile_edit', RULES[role])
                self.assertNotIn('reports:department', RULES[role])
                self.assertNotIn('reports:cooperation', RULES[role])
                self.assertNotIn('reports:account_user', RULES[role])

    def test_report_list_groups(self):
        def groups(user):
            self.client.force_login(user)
            response = self.client.get(reverse('reports:report_list'))
            return {title: [report.slug for report in reports] for title, reports in response.context['groups']}

        self.assertEqual(groups(self.student_user), {'Мои отчёты': ['form16', 'work']})
        self.assertEqual(groups(self.adjunct_user), {'Мои отчёты': ['form16', 'work', 'plan']})
        self.assertEqual(groups(self.teacher_user), {'Мои отчёты': ['form16', 'work'],
                                                     'Отчёты по подопечным': ['supervision']})
        self.assertEqual(groups(self.editor), {'Отчёты кафедры': ['form16', 'work', 'plan', 'supervision',
                                                                    'cooperation', 'department']})
        self.assertEqual(groups(self.root), {
            'Отчёты кафедры': ['form16', 'work', 'plan', 'supervision', 'cooperation', 'department'],
            'Администрирование': ['activity'],
        })
        self.assertEqual(groups(self.reader), {})

    def test_reports_block_in_cards(self):
        cases = [
            (self.teacher_user, self.student, ['form16', 'work', 'card'], ['plan', 'supervision']),
            (self.teacher_user, self.adjunct, ['form16', 'work', 'plan', 'card'], ['supervision']),
            (self.teacher_user, self.teacher, ['form16', 'work', 'supervision', 'card'], ['plan']),
            (self.editor, self.other_teacher, ['form16', 'work', 'supervision', 'card'], ['plan']),
            (self.student_user, self.student, ['form16', 'work', 'card'], ['plan', 'supervision']),
        ]
        for user, person, shown, hidden in cases:
            self.client.force_login(user)
            page = self.client.get(person.get_absolute_url())
            for name in shown:
                with self.subTest(user=user.username, person=str(person), report=name):
                    self.assertContains(page, person_report_url(name, person))
            for name in hidden:
                with self.subTest(user=user.username, person=str(person), report=name):
                    self.assertNotIn(name, [url.split('/')[2] for _, url in page.context['report_links']])
        # Пользователь без карточки видит карточку курсанта, но отчётов на него не формирует.
        self.client.force_login(self.reader)
        page = self.client.get(self.student.get_absolute_url())
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, person_report_url('card', self.student))
